#!/usr/bin/env python3
"""Adversarial eval runner for claim_lint's L7 witness check (V2-43).

A cited test is supposed to be able to fail. L7 rejects a citation when the
definition cannot fail: an empty or stub body, an unconditional skip, an
xfail, or a skip at run time. It is deliberately narrow, because a broad
"does this test really check the claim?" heuristic would flag valid tests.

Each case builds a synthetic project (a suite file, an artifact and one
claim), runs claim_lint, and pins the L7 verdict: `error`, `warning` or
`none`. The control cases exist to keep the rule from overreaching:

  * a real test next to a skipped one is not skipped by association;
  * a name defined twice is judged usable when any definition is real;
  * a report-style ID (`report("F1 ...", condition)`) is not judged at all:
    a constant condition is legitimate when the preceding statement is what
    can fail, and no safe static criterion exists.

Fixtures are synthetic and marked as such; they are not evidence about any
real suite.

Usage:
    python3 evals/claim-witness/run_evals.py [--claim-lint PATH]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TOOL = os.path.join(REPO, "tools", "claim_lint.py")

import yaml  # noqa: E402  (PyYAML is a hard dependency of claim_lint)


def ledger(tests, artifact):
    return {
        "claims": [{
            "id": "C-01",
            "claim": "The widget appends exactly one row per accepted call.",
            "mechanism": "The suite calls the widget and inspects the row count.",
            "evidence": [{
                "kind": "test",
                "tests": tests,
                "artifact": artifact,
                "date": "2026-11-08",
            }],
            "scope": "Synthetic fixture, one process.",
            "status": "tested",
        }]
    }


S = "suite/"

CASES = [
    {
        "name": "python stub with pass",
        "files": {S + "t.py": "def test_stub():\n    pass\n"},
        "tests": ["test_stub"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["has no executable statement"],
    },
    {
        "name": "python stub with only a docstring",
        "files": {S + "t.py": 'def test_stub():\n    """It will be checked later."""\n'},
        "tests": ["test_stub"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["has no executable statement"],
    },
    {
        "name": "python stub with a bare return",
        "files": {S + "t.py": "def test_stub():\n    return\n"},
        "tests": ["test_stub"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["has no executable statement"],
    },
    {
        "name": "python stub with an ellipsis",
        "files": {S + "t.py": "def test_stub():\n    ...\n"},
        "tests": ["test_stub"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["has no executable statement"],
    },
    {
        "name": "python stub in a test class",
        "files": {S + "t.py": "class TestWidget:\n    def test_stub(self):\n        pass\n"},
        "tests": ["test_stub"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["has no executable statement"],
    },
    {
        "name": "unconditional skip",
        "files": {S + "t.py": '@pytest.mark.skip(reason="later")\ndef test_later():\n    assert True\n'},
        "tests": ["test_later"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["unconditionally skipped"],
    },
    {
        "name": "xfail",
        "files": {S + "t.py": '@pytest.mark.xfail\ndef test_known_bad():\n    assert False\n'},
        "tests": ["test_known_bad"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["marked xfail"],
    },
    {
        "name": "skip at run time",
        "files": {S + "t.py": 'def test_later():\n    pytest.skip("needs a database")\n'},
        "tests": ["test_later"], "artifact": S + "t.py",
        "l7": "error", "exit": 1, "contains": ["skips at run time"],
    },
    {
        "name": "conditional skip is a warning",
        "files": {S + "t.py": '@pytest.mark.skipif(False, reason="never on this platform")\ndef test_other():\n    assert 1 == 1\n'},
        "tests": ["test_other"], "artifact": S + "t.py",
        "l7": "warning", "exit": 0, "contains": ["conditionally skipped"],
    },
    {
        "name": "rust ignore",
        "files": {S + "t.rs": "#[test]\n#[ignore]\nfn test_later() {\n    assert_eq!(1, 1);\n}\n"},
        "tests": ["test_later"], "artifact": S + "t.rs",
        "l7": "error", "exit": 1, "contains": ["marked #[ignore]"],
    },
    {
        "name": "rust empty body",
        "files": {S + "t.rs": "#[test]\nfn test_empty() {}\n"},
        "tests": ["test_empty"], "artifact": S + "t.rs",
        "l7": "error", "exit": 1, "contains": ["empty body"],
    },
    {
        "name": "real python test passes",
        "files": {S + "t.py": "def test_ok():\n    rows = append(1)\n    assert rows == 1\n"},
        "tests": ["test_ok"], "artifact": S + "t.py",
        "l7": "none", "exit": 0, "contains": [],
    },
    {
        "name": "real rust test passes",
        "files": {S + "t.rs": "#[test]\nfn test_ok() {\n    assert_eq!(append(1), 1);\n}\n"},
        "tests": ["test_ok"], "artifact": S + "t.rs",
        "l7": "none", "exit": 0, "contains": [],
    },
    {
        "name": "a skipped neighbour does not taint the cited test",
        "files": {S + "t.py": ('@pytest.mark.skip(reason="later")\n'
                               'def test_neighbour():\n    assert True\n\n'
                               "def test_cited():\n    assert append(1) == 1\n")},
        "tests": ["test_cited"], "artifact": S + "t.py",
        "l7": "none", "exit": 0, "contains": [],
    },
    {
        "name": "a real definition wins over a shadowed stub",
        "files": {S + "t.py": ("def test_widget():\n    pass\n\n"
                               "def test_widget():\n    assert append(1) == 1\n")},
        "tests": ["test_widget"], "artifact": S + "t.py",
        "l7": "none", "exit": 0, "contains": [],
    },
    {
        "name": "report-style IDs are not judged",
        "files": {S + "t.py": ('def run():\n    ok = apply()\n'
                               '    report("F1 the widget accepts a call", True)\n')},
        "tests": ["F1"], "artifact": S + "t.py",
        "l7": "none", "exit": 0, "contains": [],
    },
]


def run_case(case, tool):
    root = tempfile.mkdtemp(prefix="witness-eval-")
    try:
        for rel, content in case["files"].items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
        with open(os.path.join(root, "ledger.yaml"), "w", encoding="utf-8") as handle:
            yaml.safe_dump(ledger(case["tests"], case["artifact"]), handle,
                           allow_unicode=True, sort_keys=False)
        proc = subprocess.run(
            [sys.executable, tool, "--root", root, "--suite-glob", "suite/*",
             "--docs-glob", "no-such/*.md", "--no-vale", "ledger.yaml"],
            capture_output=True, text=True, cwd=root)
        lines = proc.stdout.splitlines()
        observed = [line.strip() for line in lines if line.strip().startswith("[L7]")]
        problems = []
        if proc.returncode != case["exit"]:
            problems.append("exit %d, expected %d" % (proc.returncode, case["exit"]))
        if case["l7"] == "none":
            if observed:
                problems.append("L7 fired on a valid test: %r" % observed)
        else:
            wanted = "[L7] %-5s" % case["l7"]
            if not any(line.startswith(wanted) for line in observed):
                problems.append("expected %s, got %r" % (wanted, observed))
        for needle in case["contains"]:
            if not any(needle in line for line in observed):
                problems.append("L7 message lacks %r" % needle)
        return problems
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--claim-lint", default=DEFAULT_TOOL)
    args = ap.parse_args()
    failed = 0
    for case in CASES:
        problems = run_case(case, args.claim_lint)
        if problems:
            failed += 1
            print("FAIL %s" % case["name"])
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % case["name"])
    total = len(CASES)
    print("%d/%d claim-witness eval cases passed" % (total - failed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
