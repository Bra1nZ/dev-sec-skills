#!/usr/bin/env python3
"""D-BOOTSTRAP: the bootstrap path is exercised end to end.

`tools/bootstrap.py` is the entry point a foreign repository uses to install
the gates. This detector runs `evals/bootstrap/run_evals.py`, which builds a
throw-away git repository, bootstraps it, promotes the open templates with a
real run and a signed run_record, and attacks the result (drift, a signed-field
edit, an escalation without evidence, a target inside the source).

The detector is deliberately thin: the eval owns the assertions. What this
file adds is a test ID the self-pilot ledger and `make verify` can resolve, so
a broken bootstrap path fails the same gate as every other detector.

Exit codes: 0 the eval passed, 1 it failed.
"""

import os
import subprocess
import sys
from pathlib import Path

# parents: [0] detectors, [1] dev-sec-skills, [2] pilots, [3] spec, [4] repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = REPO_ROOT / "evals" / "bootstrap" / "run_evals.py"


def test_bootstrap_eval_cases_pass():
    if not EVAL.is_file():
        raise AssertionError("bootstrap eval not found: %s" % EVAL)
    env = dict(os.environ)
    # Keep the eval deterministic: it passes --no-vale to claim_lint itself.
    proc = subprocess.run([sys.executable, str(EVAL)], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, env=env)
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError("bootstrap eval exited %d\n%s" % (proc.returncode, output))
    if "4/4 bootstrap eval cases passed" not in proc.stdout:
        raise AssertionError("bootstrap eval did not report 4/4\n%s" % output)
    failed = [line for line in proc.stdout.splitlines() if line.startswith("FAIL ")]
    if failed:
        raise AssertionError("bootstrap eval reported a failed case:\n%s"
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
    total = passed + failed
    tail = "%d passed" % passed
    if failed:
        tail += ", %d failed" % failed
    print("========== %s in 0.01s ==========" % tail)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
