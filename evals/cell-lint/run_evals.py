#!/usr/bin/env python3
"""Adversarial eval runner for tools/cell_lint.py.

Each case in cases/*.yaml defines a synthetic registry (and optional base
registry and claim ledger), plus expectations: for each check CL1..CL6 either a
severity that must appear ("error" | "warning" | "info") or "none". `exit` is
the expected process exit code (0 clean/warnings allowed, 1 errors found).

Fixtures are synthetic and marked as such in each file; they are not evidence
about any real project. A passing run means the linter's contract holds on the
adversarial cases, not that any production registry is clean.

Usage:
    python3 evals/cell-lint/run_evals.py [--cases DIR] [--cell-lint PATH]
"""

import argparse
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

FINDING_RE = re.compile(r"^\s*\[(CL\d)\]\s+(error|warning|info)\b")


def run_case(case_path, cell_lint):
    """Run one case; return (name, problems, stdout)."""
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    td = tempfile.mkdtemp(prefix="cell-eval-")
    try:
        for rel, content in (case.get("files") or {}).items():
            p = os.path.join(td, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)

        registry_path = os.path.join(td, "cells.yaml")
        with open(registry_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(case["registry"], f, allow_unicode=True, sort_keys=False)

        cmd = [sys.executable, cell_lint, "--root", td]
        if "base" in case:
            base_path = os.path.join(td, "cells.base.yaml")
            with open(base_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(case["base"], f, allow_unicode=True, sort_keys=False)
            cmd += ["--base", base_path]
        if "ledger" in case:
            ledger_path = os.path.join(td, "ledger.yaml")
            with open(ledger_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(case["ledger"], f, allow_unicode=True, sort_keys=False)
            cmd += ["--ledger", ledger_path]
        cmd += list(case.get("args") or [])
        cmd += [registry_path]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return name, ["cell_lint timed out"], ""

        found = {}
        for line in (r.stdout or "").splitlines():
            m = FINDING_RE.match(line)
            if m:
                found.setdefault(m.group(1), set()).add(m.group(2))
        for check, wanted in sorted((case.get("expect") or {}).items()):
            got = found.get(check, set())
            if wanted == "none":
                if got:
                    problems.append("%s: expected no findings, got %s"
                                    % (check, ",".join(sorted(got))))
            elif wanted not in got:
                problems.append("%s: expected %s, got %s"
                                % (check, wanted, ",".join(sorted(got)) or "no findings"))
        if "exit" in case and r.returncode != case["exit"]:
            problems.append("exit: expected %d, got %d" % (case["exit"], r.returncode))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return name, problems, ""


def main():
    ap = argparse.ArgumentParser(description="Adversarial evals for cell_lint")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cases", default=os.path.join(here, "cases"))
    ap.add_argument("--cell-lint",
                    default=os.path.abspath(os.path.join(here, "..", "..",
                                                         "tools", "cell_lint.py")))
    args = ap.parse_args()

    cases = sorted(f for f in os.listdir(args.cases) if f.endswith((".yaml", ".yml")))
    if not cases:
        print("no cases found in %s" % args.cases, file=sys.stderr)
        return 2

    passed, failed = 0, 0
    for fname in cases:
        name, problems, _ = run_case(os.path.join(args.cases, fname), args.cell_lint)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for p in problems:
                print("     %s" % p)
        else:
            passed += 1
            print("PASS %s" % name)
    print("evals: %d/%d passed" % (passed, passed + failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
