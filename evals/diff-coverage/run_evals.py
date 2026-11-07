#!/usr/bin/env python3
"""Adversarial eval runner for tools/diff_coverage.py.

Each case in cases/*.yaml describes a synthetic git repository (a base commit,
then a head commit), a cell registry, a claim ledger and the arguments to pass.
Expectations name DC1..DC5 and the severity that must appear ("error") or must
not ("none"); `exit` is the expected process exit code. A case may also assert
numbers in the `--json` summary through `json` (dotted keys, list indices
allowed).

The fixtures are synthetic and marked as such. They prove the gate fails closed
on the named defects; they say nothing about a real repository's coverage.

Usage:
    python3 evals/diff-coverage/run_evals.py [--cases DIR] [--tool PATH]
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

FINDING_RE = re.compile(r"^\s*\[(DC\d)\]\s+(error)\b")


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


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), proc.stderr))
    return proc.stdout.strip()


def build_repo(td, case):
    _git(td, "init", "-q")
    _git(td, "config", "user.email", "eval@example.invalid")
    _git(td, "config", "user.name", "eval")
    for rel, content in (case.get("base_files") or {}).items():
        _write(td, rel, content)
    _git(td, "add", "-A")
    _git(td, "commit", "-q", "--allow-empty", "-m", "base")
    base = _git(td, "rev-parse", "HEAD")
    for rel, content in (case.get("head_files") or {}).items():
        _write(td, rel, content)
    for rel in case.get("delete_head") or []:
        path = os.path.join(td, rel)
        if os.path.exists(path):
            os.remove(path)
    for old, new in (case.get("rename_head") or {}).items():
        os.makedirs(os.path.dirname(os.path.join(td, new)) or td, exist_ok=True)
        _git(td, "mv", old, new)
    _git(td, "add", "-A")
    _git(td, "commit", "-q", "--allow-empty", "-m", "head")
    head = _git(td, "rev-parse", "HEAD")
    return base, head


def run_case(case_path, tool):
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    td = tempfile.mkdtemp(prefix="diff-coverage-eval-")
    outside = tempfile.mkdtemp(prefix="diff-coverage-input-")
    try:
        base, head = build_repo(td, case)
        cells = os.path.join(outside, "cells.yaml")
        ledger = os.path.join(outside, "ledger.yaml")
        _write(outside, "cells.yaml", case["cells"])
        _write(outside, "ledger.yaml", case["ledger"])

        args = ["--repo", td, "--base", base, "--head", head,
                "--cells", cells, "--ledger", ledger]
        args += [str(a) for a in case.get("args") or []]
        json_path = None
        if case.get("json") is not None:
            json_path = os.path.join(outside, "report.json")
            args += ["--json", json_path]

        cmd = [sys.executable, tool] + args
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != case.get("exit"):
            problems.append("exit: expected %s, got %d" % (case.get("exit"), r.returncode))
        seen = {}
        for line in r.stdout.splitlines():
            match = FINDING_RE.match(line)
            if match:
                seen[match.group(1)] = seen.get(match.group(1), 0) + 1
        for check, wanted in (case.get("expect") or {}).items():
            got = "error" if seen.get(check) else "none"
            if got != wanted:
                problems.append("%s: expected %s, got %s" % (check, wanted, got))
        if json_path and os.path.exists(json_path):
            report = json.load(open(json_path, encoding="utf-8"))
            for key, wanted in (case.get("json") or {}).items():
                got = _dotted(report, key)
                if got != wanted:
                    problems.append("json %s: expected %r, got %r" % (key, wanted, got))
        elif case.get("json") is not None:
            problems.append("json report was not written")
        if r.returncode == 2 and case.get("exit") != 2:
            problems.append("usage error: %s" % r.stderr.strip()[:200])
    finally:
        shutil.rmtree(td, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
    return name, problems


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default=os.path.join(here, "cases"))
    ap.add_argument("--tool", default=os.path.join(here, "..", "..", "tools",
                                                   "diff_coverage.py"))
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.cases) if f.endswith((".yaml", ".yml")))
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
    print("%d/%d diff-coverage eval cases passed" % (len(files) - failed, len(files)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
