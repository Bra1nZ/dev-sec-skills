#!/usr/bin/env python3
"""Adversarial eval runner for tools/fuzz_triage.py.

Each case in cases/*.yaml defines a fuzz run record, a triage file, optional
cell registry and mutation fixtures, and expectations: for each check T1..T4
either a severity that must appear ("error") or "none". `exit` is the expected
process exit code.

Fixtures are synthetic and marked as such; they prove the gate fails closed on
the named defects, not that any real finding was triaged.

Usage:
    python3 evals/fuzz-triage/run_evals.py [--cases DIR] [--tool PATH]
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

FINDING_RE = re.compile(r"^\s*\[(T\d)\]\s+(error)\b")


def _write(root, rel, content):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        else:
            json.dump(content, f, indent=2)
            f.write("\n")


def run_case(case_path, tool):
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    td = tempfile.mkdtemp(prefix="fuzz-triage-eval-")
    try:
        for rel, content in (case.get("files") or {}).items():
            _write(td, rel, content)
        _write(td, "record.json", case["record"])
        with open(os.path.join(td, "triage.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(case["triage"], f, allow_unicode=True, sort_keys=False)

        cmd = [sys.executable, tool, "--record", "record.json",
               "--triage", "triage.yaml"] + [str(a) for a in case.get("args") or []]
        r = subprocess.run(cmd, cwd=td, capture_output=True, text=True, timeout=60)
        if r.returncode != case.get("exit"):
            problems.append("exit: expected %s, got %d" % (case.get("exit"), r.returncode))
        seen = {}
        for line in r.stdout.splitlines():
            m = FINDING_RE.match(line)
            if m:
                seen[m.group(1)] = seen.get(m.group(1), 0) + 1
        for check, wanted in (case.get("expect") or {}).items():
            got = "error" if seen.get(check) else "none"
            if got != wanted:
                problems.append("%s: expected %s, got %s" % (check, wanted, got))
        if r.returncode == 2:
            problems.append("usage error: %s" % (r.stderr.strip()[:200]))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return name, problems


def main():
    ap = argparse.ArgumentParser(description="Adversarial evals for fuzz_triage")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cases", default=os.path.join(here, "cases"))
    ap.add_argument("--tool",
                    default=os.path.abspath(os.path.join(here, "..", "..",
                                                         "tools", "fuzz_triage.py")))
    args = ap.parse_args()

    cases = sorted(f for f in os.listdir(args.cases) if f.endswith((".yaml", ".yml")))
    if not cases:
        print("no cases found in %s" % args.cases, file=sys.stderr)
        return 2

    passed, failed = 0, 0
    for fname in cases:
        name, problems = run_case(os.path.join(args.cases, fname), args.tool)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for problem in problems:
                print("     %s" % problem)
        else:
            passed += 1
            print("PASS %s" % name)
    print("evals: %d/%d passed" % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
