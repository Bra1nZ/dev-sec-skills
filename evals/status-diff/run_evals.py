#!/usr/bin/env python3
"""Adversarial evals for tools/status_diff.py base handling.

The gate must fail closed: a missing ref, a missing base ledger, or an empty
base ledger may not silently disable the status-escalation check. The
``redating-known-gap`` scenario reproduces a still-open hole and is reported
separately instead of being counted as a pass.

Fixtures are synthetic and are not evidence about any real project.

Usage:
    python3 evals/status-diff/run_evals.py [--status-diff PATH]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

CLAIM = """\
  - id: C-01
    claim: "Synthetic claim."
    mechanism: "Synthetic mechanism."
    status: {status}
    scope:
      platforms: "any"
    evidence:
{evidence}
    limitations: "Synthetic fixture."
"""

EVIDENCE = """\
      - kind: test
        tests: [F1]
        command: "python3 setup/test_x.py"
        artifact: "setup/test_x.py"
        date: "{date}"
"""


def ledger(status, evidence):
    return "project: synthetic\ngenerated: \"2026-11-06\"\nclaims:\n" + CLAIM.format(
        status=status, evidence=evidence)


def git(td, *args, check=True):
    r = subprocess.run(["git"] + list(args), cwd=td, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), r.stderr))
    return r


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_repo(base_text, target_text):
    """Init a repo, commit base_text (if any), then write target_text."""
    td = tempfile.mkdtemp(prefix="sd-eval-")
    git(td, "init", "-q")
    git(td, "config", "user.email", "eval@example.invalid")
    git(td, "config", "user.name", "eval")
    rel = os.path.join(td, "docs", "claims.yaml")
    if base_text is not None:
        write(rel, base_text)
    git(td, "add", "-A")
    git(td, "commit", "-q", "--allow-empty", "-m", "base")
    if target_text is not None:
        write(rel, target_text)
    return td


def run(status_diff, td, extra=()):
    cmd = [sys.executable, status_diff, "--repo", td,
           "--ledger", "docs/claims.yaml"]
    cmd += list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return r


def scenarios():
    """Return (name, base_text, target_text, args, expected_exit, known_gap)."""
    e1 = EVIDENCE.format(date="2026-10-30")
    e2 = EVIDENCE.format(date="2026-11-06")
    open_e1 = ledger("open", e1)
    tested_e1 = ledger("tested", e1)
    tested_e1e2 = ledger("tested", e1 + e2)
    empty = "project: synthetic\ngenerated: \"2026-10-30\"\nclaims: []\n"

    return [
        ("missing-ref", open_e1, tested_e1, ["--git-ref", "no-such-tag"], 1, False),
        ("missing-ref-first-release", open_e1, tested_e1,
         ["--git-ref", "no-such-tag", "--first-release"], 0, False),
        ("ledger-absent-at-base", None, open_e1, ["--git-ref", "HEAD"], 1, False),
        ("ledger-absent-first-release", None, open_e1,
         ["--git-ref", "HEAD", "--first-release"], 0, False),
        ("empty-base-claims", empty, open_e1, ["--git-ref", "HEAD"], 1, False),
        ("empty-base-first-release", empty, open_e1,
         ["--git-ref", "HEAD", "--first-release"], 0, False),
        ("escalation-without-evidence", open_e1, tested_e1, ["--git-ref", "HEAD"], 1, False),
        ("escalation-with-new-evidence", open_e1, tested_e1e2, ["--git-ref", "HEAD"], 0, False),
        ("redating-known-gap", open_e1,
         ledger("tested", EVIDENCE.format(date="2026-11-06")),
         ["--git-ref", "HEAD"], 0, True),
    ]


def main():
    ap = argparse.ArgumentParser(description="Adversarial evals for status_diff")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--status-diff",
                    default=os.path.abspath(os.path.join(here, "..", "..",
                                                         "tools", "status_diff.py")))
    args = ap.parse_args()

    passed, failed, gaps = 0, 0, 0
    for name, base, target, extra, want_exit, known_gap in scenarios():
        td = make_repo(base, target)
        try:
            r = run(args.status_diff, td, extra)
        finally:
            shutil.rmtree(td, ignore_errors=True)
        if r.returncode == want_exit:
            if known_gap:
                gaps += 1
                print("GAP  %s (expected exit %d; still open)" % (name, want_exit))
            else:
                passed += 1
                print("PASS %s" % name)
        else:
            failed += 1
            print("FAIL %s: expected exit %d, got %d" % (name, want_exit, r.returncode))
            for stream in (r.stdout, r.stderr):
                for line in (stream or "").splitlines():
                    print("     %s" % line)
    print("evals: %d passed, %d failed, %d known gap(s)" % (passed, failed, gaps))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
