#!/usr/bin/env python3
"""D-CLAIM-WITNESS: claim_lint's L7 witness check is exercised end to end.

L7 asks a narrow question: can the cited test fail at all? It rejects a stub
body (`pass`, a docstring, a bare `return`, an ellipsis), an unconditional
skip, an xfail and a skip at run time; it warns on a conditional skip, and it
leaves report-style IDs alone because no safe static criterion exists for
them.

This detector runs `evals/claim-witness/run_evals.py`, which builds synthetic
Python and Rust suites and pins the verdict for each case, including the
controls that keep the rule from overreaching (a skipped neighbour, a
shadowed stub next to a real definition, a real report call).

The detector is deliberately thin: the eval owns the assertions. What this
file adds is a test ID the self-pilot ledger and `make verify` can resolve.

Exit codes: 0 the eval passed, 1 it failed.
"""

import os
import subprocess
import sys
from pathlib import Path

# parents: [0] detectors, [1] dev-sec-skills, [2] pilots, [3] spec, [4] repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = REPO_ROOT / "evals" / "claim-witness" / "run_evals.py"
EXPECTED = "16/16 claim-witness eval cases passed"


def test_claim_witness_eval_cases_pass():
    if not EVAL.is_file():
        raise AssertionError("claim-witness eval not found: %s" % EVAL)
    proc = subprocess.run([sys.executable, str(EVAL)], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=dict(os.environ))
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError("claim-witness eval exited %d\n%s"
                             % (proc.returncode, output))
    if EXPECTED not in proc.stdout:
        raise AssertionError("claim-witness eval did not report %r\n%s"
                             % (EXPECTED, output))
    failed = [line for line in proc.stdout.splitlines() if line.startswith("FAIL ")]
    if failed:
        raise AssertionError("claim-witness eval reported a failed case:\n%s"
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
