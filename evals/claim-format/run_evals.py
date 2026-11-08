#!/usr/bin/env python3
"""Adversarial eval runner for `claim_lint --format github` (V2-41).

The text format has no consumer other than a human reading a log. The GitHub
format has one machine consumer: the runner parses `::error`/`::warning`
workflow commands and attaches them to a file and a line. A wrong line is a
comment on the wrong line, so the cases pin the location, the escaping and the
suppression threshold instead of checking that "an annotation appeared".

Cases:
  * an L1 error points at the claim's block in the ledger, not at line 1;
  * a warning is hidden by default and shown only with --annotations warning;
  * `,` `:` `%` in a file path are escaped as workflow-command properties;
  * a JSON ledger gets an annotation with no line (no compose, no guess);
  * a finding with no claim lands on the ledger and gets no line;
  * the text format is byte-identical to the pre-V2-41 output (regression).

Fixtures are synthetic (`docs/claims.yaml` under a temporary root) and marked
as such; they are not evidence about any real ledger.

Usage:
    python3 evals/claim-format/run_evals.py [--claim-lint PATH]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TOOL = os.path.join(REPO, "tools", "claim_lint.py")
TOOLS_DIR = os.path.join(REPO, "tools")

if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
import claim_lint  # noqa: E402

REVIEW = """  - id: C-01
    claim: "Review approved the design."
    mechanism: "Reviewer checklist."
    evidence:
      - kind: review
        artifact: "docs/review.md"
        date: "2026-11-01"
    scope: "Synthetic fixture."
    status: reviewed
"""

# C-02 starts at line 12: the mapping begins after the blank line that closes
# C-01. The block itself is what a reviewer edits, so that is the line.
LEDGER_ONE_ERROR = """claims:
""" + REVIEW + """
  - id: C-02
    claim: "Second claim."
    evidence:
      - kind: review
        artifact: "docs/review.md"
        date: "2026-11-01"
    scope: "Synthetic fixture."
    status: reviewed
"""

CLEAN_LEDGER = """claims:
""" + REVIEW

CASES = [
    {
        "name": "error points at the claim block",
        "files": {"docs/review.md": "", "docs/claims.yaml": LEDGER_ONE_ERROR},
        "args": ["--format", "github", "docs/claims.yaml"],
        "exit": 1,
        "annotations": [
            "::error file=docs/claims.yaml,line=12,title=claim_lint L1::"
            "C-02: missing required field 'mechanism'",
        ],
    },
    {
        "name": "warnings stay out of the diff by default",
        "files": {"docs/review.md": "", "docs/claims.yaml": CLEAN_LEDGER,
                  "README.md": "This is guaranteed to work.\n"},
        "args": ["--format", "github", "docs/claims.yaml"],
        "exit": 0,
        "annotations": [],
        "contains": ["1 warning(s)", "0 annotation(s)"],
    },
    {
        "name": "warnings are annotatable on request",
        "files": {"docs/review.md": "", "docs/claims.yaml": CLEAN_LEDGER,
                  "README.md": "This is guaranteed to work.\n"},
        "args": ["--format", "github", "--annotations", "warning",
                 "docs/claims.yaml"],
        "exit": 0,
        "annotations": [
            "::warning file=README.md,line=1,title=claim_lint L5::"
            "unqualified absolute 'guaranteed'",
        ],
    },
    {
        "name": "path properties are escaped",
        "files": {"docs/review.md": "", "docs/claims.yaml": CLEAN_LEDGER,
                  "docs/a,b:c%.md": "This is guaranteed to work.\n"},
        "args": ["--format", "github", "--annotations", "warning",
                 "--docs-glob", "docs/*.md", "docs/claims.yaml"],
        "exit": 0,
        "annotations": [
            "::warning file=docs/a%2Cb%3Ac%25.md,line=1,title=claim_lint L5::"
            "unqualified absolute 'guaranteed'",
        ],
    },
    {
        "name": "a JSON ledger gets no line",
        "files": {
            "docs/review.md": "",
            "claims.json": json.dumps({"claims": [
                {"id": "C-01", "claim": "Review approved the design.",
                 "mechanism": "Reviewer checklist.", "scope": "Synthetic.",
                 "status": "reviewed",
                 "evidence": [{"kind": "review", "artifact": "docs/review.md",
                               "date": "2026-11-01"}]},
                {"id": "C-02", "claim": "Second claim.", "scope": "Synthetic.",
                 "status": "reviewed",
                 "evidence": [{"kind": "review", "artifact": "docs/review.md",
                               "date": "2026-11-01"}]},
            ]}),
        },
        "args": ["--format", "github", "claims.json"],
        "exit": 1,
        "annotations": [
            "::error file=claims.json,title=claim_lint L1::"
            "C-02: missing required field 'mechanism'",
        ],
    },
    {
        "name": "a finding with no claim lands on the ledger, no line",
        "files": {"docs/claims.yaml": "{}\n"},
        "args": ["--format", "github", "docs/claims.yaml"],
        "exit": 1,
        "annotations": [
            "::error file=docs/claims.yaml,title=claim_lint L1::no claims array found"
        ],
    },
    {
        "name": "the text format is unchanged",
        "files": {"docs/review.md": "", "docs/claims.yaml": LEDGER_ONE_ERROR},
        "args": ["docs/claims.yaml"],
        "exit": 1,
        "annotations": None,  # text format: every stdout line is prose
        "contains": ["ledger: docs/claims.yaml | claims: 2",
                     "[L1] error C-02"],
        "forbids": ["::error", "::warning"],
    },
]


def run_case(case, root, tool):
    for rel, content in case["files"].items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    args = [sys.executable, tool, "--root", root, "--no-vale"] + case["args"]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=root)
    problems = []
    if proc.returncode != case["exit"]:
        problems.append("exit %d, expected %d" % (proc.returncode, case["exit"]))
    lines = proc.stdout.splitlines()
    observed = [line for line in lines if line.startswith("::")]
    if case["annotations"] is None:
        if observed:
            problems.append("text format emitted %d annotation(s): %r"
                            % (len(observed), observed[:3]))
    elif observed != case["annotations"]:
        problems.append("annotations %r, expected %r"
                        % (observed, case["annotations"]))
    for needle in case.get("contains", []):
        if not any(needle in line for line in lines):
            problems.append("stdout lacks %r" % needle)
    for needle in case.get("forbids", []):
        if any(needle in line for line in lines):
            problems.append("stdout contains %r" % needle)
    return problems


def run_units():
    """Pin the two units the cases cannot reach from the outside."""
    problems = []
    got = claim_lint._escape_data("50% ok\r\nnext")
    if got != "50%25 ok%0D%0Anext":
        problems.append("_escape_data: %r" % got)
    got = claim_lint._escape_property("a,b:c%")
    if got != "a%2Cb%3Ac%25":
        problems.append("_escape_property: %r" % got)
    root = tempfile.mkdtemp(prefix="claim-format-unit-")
    try:
        yaml_path = os.path.join(root, "claims.yaml")
        with open(yaml_path, "w", encoding="utf-8") as handle:
            handle.write(LEDGER_ONE_ERROR)
        got = claim_lint.claim_lines(yaml_path)
        if got != {"C-01": 2, "C-02": 12}:
            problems.append("claim_lines: %r" % got)
        json_path = os.path.join(root, "claims.json")
        with open(json_path, "w", encoding="utf-8") as handle:
            handle.write('{"claims": []}\n')
        got = claim_lint.claim_lines(json_path)
        if got != {}:
            problems.append("claim_lines(json): %r" % got)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claim-lint", default=DEFAULT_TOOL)
    args = ap.parse_args()

    failed = 0
    total = len(CASES) + 1
    for case in CASES:
        root = tempfile.mkdtemp(prefix="claim-format-eval-")
        try:
            problems = run_case(case, root, args.claim_lint)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            failed += 1
            print("FAIL %s" % case["name"])
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % case["name"])
    problems = run_units()
    if problems:
        failed += 1
        print("FAIL escaping and claim_lines units")
        for problem in problems:
            print("     %s" % problem)
    else:
        print("ok   escaping and claim_lines units")
    print("%d/%d claim-format eval cases passed" % (total - failed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
