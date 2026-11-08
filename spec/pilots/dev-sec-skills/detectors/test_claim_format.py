#!/usr/bin/env python3
"""D-CLAIM-FORMAT: `claim_lint --format github` is exercised end to end (V2-41).

The text format has one reader, a human. The GitHub format has a machine
reader: the runner parses `::error`/`::warning` commands and attaches them to a
file and a line. This detector runs `evals/claim-format/run_evals.py`, which
pins the location (a claim's own block, not line 1), the escaping of `,` `:`
`%` in properties, the warning threshold, the JSON-ledger case without a line,
and — as a regression — that the text format did not change.

The detector is deliberately thin: the eval owns the assertions. What this
file adds is a test ID the self-pilot ledger and `make verify` can resolve, so
a broken annotation format fails the same gate as every other detector.

Exit codes: 0 the eval passed, 1 it failed.
"""

import os
import subprocess
import sys
from pathlib import Path

# parents: [0] detectors, [1] dev-sec-skills, [2] pilots, [3] spec, [4] repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = REPO_ROOT / "evals" / "claim-format" / "run_evals.py"
EXPECTED = "8/8 claim-format eval cases passed"


def test_claim_format_eval_cases_pass():
    if not EVAL.is_file():
        raise AssertionError("claim-format eval not found: %s" % EVAL)
    proc = subprocess.run([sys.executable, str(EVAL)], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=dict(os.environ))
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError("claim-format eval exited %d\n%s"
                             % (proc.returncode, output))
    if EXPECTED not in proc.stdout:
        raise AssertionError("claim-format eval did not report %r\n%s"
                             % (EXPECTED, output))
    failed = [line for line in proc.stdout.splitlines() if line.startswith("FAIL ")]
    if failed:
        raise AssertionError("claim-format eval reported a failed case:\n%s"
                             % "\n".join(failed))


# -------------------------------------------------------------------- main

def main():
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    passed = 0
    failed = 0
    for name, test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print("%s ... failed" % name)
            print("    %s" % exc)
        else:
            passed += 1
            print("%s ... ok" % name)
    tail = "%d passed" % passed
    if failed:
        tail += ", %d failed" % failed
    print("========== %s ==========" % tail)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
