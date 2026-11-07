#!/usr/bin/env python3
"""D-PINNED-ACTIONS: every action a workflow runs is pinned to a commit SHA.

The detector scans the `uses:` references of GitHub Actions workflows and
rejects a mutable tag or branch (`@v7`, `@main`, `@master`). A tag can be
retagged after review, so the code the job runs is not the code that was
reviewed.

The file is deliberately dependency-free. Its `def test_*` functions are the
test IDs `tools/cell_lint.py` resolves through `--suite-glob`, and the same
functions run under `python3 <this file>` with a pytest-shaped log, so the
detector needs neither pytest nor a network. The workflow root is
`.github/workflows` of this repository unless `DEVSEC_WORKFLOWS_ROOT` names
another directory; the mutation fixtures use that override to point the same
check at a throw-away copy.

Exit codes: 0 every test passed, 1 at least one test failed.
"""

import os
import re
import sys
from pathlib import Path

# parents: [0] detectors, [1] dev-sec-skills, [2] pilots, [3] spec, [4] repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ROOT = REPO_ROOT / ".github" / "workflows"

# A `uses:` value, optionally quoted, on a step line. `#` starts a comment.
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)")
SHA_REF_RE = re.compile(r"@[0-9a-f]{40}$")
LOCAL_PREFIXES = ("./", "../")
# Docker image references are pinned by digest, not by a commit SHA; they are a
# different failure class and out of this detector's scope.
NON_ACTION_PREFIXES = ("docker://",)


def workflows_root():
    override = os.environ.get("DEVSEC_WORKFLOWS_ROOT")
    return Path(override) if override else DEFAULT_ROOT


def workflow_files(root):
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.suffix in (".yml", ".yaml"))


def iter_action_refs(root):
    """Yield (path, line_number, ref) for every non-local `uses:` reference."""
    for path in workflow_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            match = USES_RE.match(line)
            if not match:
                continue
            ref = match.group(1)
            if ref.startswith(LOCAL_PREFIXES) or ref.startswith(NON_ACTION_PREFIXES):
                continue
            yield path, number, ref


def is_pinned(ref):
    return bool(SHA_REF_RE.search(ref))


# ------------------------------------------------------------------- tests

def test_workflow_files_exist():
    root = workflows_root()
    files = workflow_files(root)
    assert files, "no workflow files under %s" % root


def test_workflows_use_at_least_one_action():
    refs = list(iter_action_refs(workflows_root()))
    assert refs, "no actionable `uses:` reference under %s; the pin check would be vacuous" % workflows_root()


def test_workflow_actions_are_pinned():
    bad = []
    for path, number, ref in iter_action_refs(workflows_root()):
        if not is_pinned(ref):
            bad.append("%s:%d %s" % (path.name, number, ref))
    assert not bad, "mutable action reference(s): " + "; ".join(bad)


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
