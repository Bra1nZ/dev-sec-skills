#!/usr/bin/env python3
"""Adversarial eval runner for tools/fuzz_run.py.

Each case in cases/*.yaml defines a synthetic project (files), a target
command, adapter arguments and expectations about the produced record:
`verdict`, the exact number of `findings`, `stopped_early`, and
`digests_equal` (run the same case twice and require the same
executions_digest, which is the determinism claim).

Fixtures are synthetic and marked as such; they prove the adapter's contract,
not that any real target is free of bugs.

Usage:
    python3 evals/fuzz/run_evals.py [--cases DIR] [--fuzz-run PATH]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _write(root, rel, content):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _run_once(case, td, fuzz_run, tag):
    record = os.path.join(td, "record-%s.json" % tag)
    cmd = [sys.executable, fuzz_run,
           "--target", case["target"],
           "--corpus", os.path.join(td, "corpus"),
           "--record", record,
           "--cwd", td]
    cmd += [str(a) for a in (case.get("args") or [])]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    data = None
    if os.path.exists(record):
        with open(record, encoding="utf-8") as f:
            data = json.load(f)
    return r, data


def run_case(case_path, fuzz_run):
    case = yaml.safe_load(open(case_path, encoding="utf-8"))
    name = case.get("name") or os.path.basename(case_path)
    problems = []
    td = tempfile.mkdtemp(prefix="fuzz-eval-")
    try:
        for rel, content in (case.get("files") or {}).items():
            _write(td, rel, content)
        expect = case.get("expect") or {}
        r, data = _run_once(case, td, fuzz_run, "a")
        if r.returncode != case.get("exit"):
            problems.append("exit: expected %s, got %d" % (case.get("exit"), r.returncode))
        if data is None:
            if expect.get("record", True):
                problems.append("no record was written")
        else:
            for field, wanted in (("verdict", expect.get("verdict")),):
                if wanted is not None and data.get(field) != wanted:
                    problems.append("%s: expected %r, got %r" % (field, wanted, data.get(field)))
            if "findings" in expect and len(data.get("findings") or []) != expect["findings"]:
                problems.append("findings: expected %d, got %d"
                                % (expect["findings"], len(data.get("findings") or [])))
            if "stopped_early" in expect:
                got = (data.get("budget") or {}).get("stopped_early")
                if got != expect["stopped_early"]:
                    problems.append("stopped_early: expected %r, got %r"
                                    % (expect["stopped_early"], got))
            if "seed_input" in expect:
                seeds = [f.get("seed_input") for f in data.get("findings") or []]
                if expect["seed_input"] not in seeds:
                    problems.append("seed_input %r not found in findings" % expect["seed_input"])
            if expect.get("digests_equal"):
                r2, data2 = _run_once(case, td, fuzz_run, "b")
                if r2.returncode != case.get("exit"):
                    problems.append("second run exit: expected %s, got %d"
                                    % (case.get("exit"), r2.returncode))
                if data2 is None:
                    problems.append("second run wrote no record")
                elif data.get("executions_digest") != data2.get("executions_digest"):
                    problems.append("executions_digest differs between identical runs: %s vs %s"
                                    % (data.get("executions_digest"),
                                       data2.get("executions_digest")))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return name, problems


def main():
    ap = argparse.ArgumentParser(description="Adversarial evals for fuzz_run")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cases", default=os.path.join(here, "cases"))
    ap.add_argument("--fuzz-run",
                    default=os.path.abspath(os.path.join(here, "..", "..",
                                                         "tools", "fuzz_run.py")))
    args = ap.parse_args()

    cases = sorted(f for f in os.listdir(args.cases) if f.endswith((".yaml", ".yml")))
    if not cases:
        print("no cases found in %s" % args.cases, file=sys.stderr)
        return 2

    passed, failed = 0, 0
    for fname in cases:
        name, problems = run_case(os.path.join(args.cases, fname), args.fuzz_run)
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
