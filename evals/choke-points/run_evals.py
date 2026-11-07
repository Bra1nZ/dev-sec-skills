#!/usr/bin/env python3
"""Adversarial eval runner for tools/choke_points.py.

Each case in cases/*.yaml describes a synthetic tree, an optional inline rules
file, and the arguments to pass. Expectations can name CP1/CP2 severity, the
process exit code, numbers in the `--json` report (dotted keys), per-candidate
fields (span, rule, signals, classification) and symbols that must not appear.

The fixtures are synthetic and marked as such. They prove the extractor and the
rule gate behave as specified on the named defects; they say nothing about any
real repository's choke points.

Usage:
    python3 evals/choke-points/run_evals.py [--cases DIR] [--tool PATH]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

FINDING_RE = re.compile(r"^\s*\[(CP\d)\]\s+(error)\b")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_RULES = os.path.join(REPO, "spec", "choke-points", "rules.yaml")
DEFAULT_SCHEMA = os.path.join(REPO, "spec", "conveyor",
                              "cell-registry.schema.json")


def _write(root, rel, content):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        else:
            yaml.safe_dump(content, f, allow_unicode=True, sort_keys=False)


def _dotted(data, key):
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return "<missing>"
    return node


def _candidate(report, expected):
    symbol = expected["symbol"]
    path = expected.get("path")
    for candidate in report.get("candidates") or []:
        names = {candidate.get("symbol"), candidate.get("qualname")}
        if symbol not in names and not str(candidate.get("qualname", "")).endswith(
                "." + symbol):
            continue
        if path and candidate.get("path") != path:
            continue
        return candidate
    return None


def run_case(case_path, tool):
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    td = tempfile.mkdtemp(prefix="choke-points-eval-")
    try:
        for rel, content in (case.get("files") or {}).items():
            _write(td, rel, content)

        args = ["--root", str(case.get("root", "."))]
        if case.get("rules") is not None:
            _write(td, "rules.yaml", case["rules"])
            args += ["--rules", "rules.yaml"]
        elif case.get("rules_path"):
            args += ["--rules", str(case["rules_path"])]
        else:
            args += ["--rules", DEFAULT_RULES]
        if case.get("schema") is not None:
            _write(td, "schema.json", case["schema"])
            args += ["--schema", "schema.json"]
        elif case.get("schema_path"):
            args += ["--schema", str(case["schema_path"])]
        elif not case.get("no_schema"):
            args += ["--schema", DEFAULT_SCHEMA]
        for pattern in case.get("globs") or []:
            args += ["--glob", str(pattern)]
        args += [str(a) for a in case.get("args") or []]

        json_path = None
        if case.get("json") is not None or case.get("candidates") is not None \
                or case.get("absent") is not None:
            json_path = os.path.join(td, "report.json")
            args += ["--json", json_path]

        cmd = [sys.executable, tool] + args
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True,
                           timeout=60)
        if r.returncode != case.get("exit"):
            problems.append("exit: expected %s, got %d"
                            % (case.get("exit"), r.returncode))
        seen = {}
        for line in r.stdout.splitlines():
            match = FINDING_RE.match(line)
            if match:
                seen[match.group(1)] = seen.get(match.group(1), 0) + 1
        for check, wanted in (case.get("expect") or {}).items():
            got = "error" if seen.get(check) else "none"
            if got != wanted:
                problems.append("%s: expected %s, got %s"
                                % (check, wanted, got))
        for needle in case.get("stderr") or []:
            if needle not in r.stderr:
                problems.append("stderr: %r not found in %r"
                                % (needle, r.stderr.strip()[:200]))

        report = None
        if json_path and os.path.exists(json_path):
            report = json.load(open(json_path, encoding="utf-8"))
            for key, wanted in (case.get("json") or {}).items():
                got = _dotted(report, key)
                if got != wanted:
                    problems.append("json %s: expected %r, got %r"
                                    % (key, wanted, got))
            for expected in case.get("candidates") or []:
                found = _candidate(report, expected)
                if found is None:
                    problems.append("candidate %r: not found"
                                    % expected["symbol"])
                    continue
                for key, wanted in expected.items():
                    if key in ("symbol", "path"):
                        continue
                    got = found.get(key)
                    if key == "signals":
                        same = set(got or []) == set(wanted or [])
                    else:
                        same = got == wanted
                    if not same:
                        problems.append("candidate %r %s: expected %r, got %r"
                                        % (expected["symbol"], key, wanted, got))
            for symbol in case.get("absent") or []:
                if _candidate(report, {"symbol": symbol}) is not None:
                    problems.append("candidate %r: expected absent, found"
                                    % symbol)
        elif json_path:
            problems.append("json report was not written")
        if r.returncode == 2 and case.get("exit") != 2:
            problems.append("usage error: %s" % r.stderr.strip()[:200])
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return name, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default=os.path.join(HERE, "cases"))
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "choke_points.py"))
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.cases)
                   if f.endswith((".yaml", ".yml")))
    if not files:
        print("no cases in %s" % args.cases, file=sys.stderr)
        return 2
    failed = 0
    for rel in files:
        name, problems = run_case(os.path.join(args.cases, rel), args.tool)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % name)
    print("%d/%d choke-points eval cases passed"
          % (len(files) - failed, len(files)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
