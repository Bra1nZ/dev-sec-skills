#!/usr/bin/env python3
"""D-JOURNAL: the verdict journal gate is exercised end to end.

`tools/verdict_journal.py` is what keeps a verdict from disappearing: a hash
chain over every recorded claim, checked against the committed ledgers and a
signed head. This detector runs `evals/journal/run_evals.py`, which builds a
throw-away git repository with two ledgers and a key outside it, appends a
journal, and attacks it (a status or evidence change with no entry, a retired
claim with no tombstone, an edited or dropped entry, a truncated history, a
tampered or rewritten head, a prose edit the head no longer covers, a
foreign signer, and an append that must refuse a broken chain or head).

The detector is deliberately thin: the eval owns the assertions. What this
file adds is a test ID the self-pilot ledger and `make verify` can resolve, so
a broken journal gate fails the same gate as every other detector.

Exit codes: 0 the eval passed, 1 it failed.
"""

import os
import subprocess
import sys
from pathlib import Path

# parents: [0] detectors, [1] dev-sec-skills, [2] pilots, [3] spec, [4] repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = REPO_ROOT / "evals" / "journal" / "run_evals.py"
EXPECTED = "14/14 journal eval cases passed"


def test_verdict_journal_eval_cases_pass():
    if not EVAL.is_file():
        raise AssertionError("journal eval not found: %s" % EVAL)
    proc = subprocess.run([sys.executable, str(EVAL)], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=dict(os.environ))
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError("journal eval exited %d\n%s" % (proc.returncode, output))
    if EXPECTED not in proc.stdout:
        raise AssertionError("journal eval did not report %r\n%s"
                             % (EXPECTED, output))
    failed = [line for line in proc.stdout.splitlines() if line.startswith("FAIL ")]
    if failed:
        raise AssertionError("journal eval reported a failed case:\n%s"
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
    print("========== %s in 0.01s ==========" % tail)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
