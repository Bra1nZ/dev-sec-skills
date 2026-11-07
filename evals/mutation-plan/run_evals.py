#!/usr/bin/env python3
"""Adversarial eval runner for tools/mutation_plan.py (V2-11).

Each scenario builds a throw-away git repository with a base and a head commit,
writes synthetic fixtures/registries, and runs the planner. The scenarios are
synthetic and marked as such: they prove the selector reacts to the named diff
shapes, not that any real pilot changes as expected.

Usage:
    python3 evals/mutation-plan/run_evals.py [--tool PATH]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

FIXTURE = {"id": "MUT-001", "cell": "CELL-001", "artifact": "src/a.py"}


def _write(root, rel, content):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if content is None:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        else:
            yaml.safe_dump(content, f, allow_unicode=True, sort_keys=False)


def _git(root, *argv):
    proc = subprocess.run(["git", "-C", root] + list(argv),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("git %s: %s"
                           % (" ".join(argv), proc.stderr.strip()))
    return proc.stdout


def _init(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "eval@example.invalid")
    _git(root, "config", "user.name", "eval")
    _git(root, "config", "commit.gpgsign", "false")


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _registry(*cells):
    return {"cells": list(cells)}


def _cell(cell_id, enforced_at=None, detectors=None):
    cell = {
        "id": cell_id,
        "title": "A synthetic invariant for the planner eval.",
        "taxonomy_class": "security",
        "failure_class": "synthetic",
        "entry_points": ["http"],
        "failure_mode": "deny",
        "coverage_status": "tested",
        "owner": "eval",
        "detectors": detectors or [],
    }
    if enforced_at:
        cell["enforced_at"] = enforced_at
    return cell


SCENARIOS = [
    {
        "name": "clean-control-no-selection",
        "base": {"src/a.py": "x = 1\n", "src/guard.py": "def guard():\n    pass\n"},
        "head": {"src/note.md": "unrelated\n"},
        "cells": _registry(_cell("CELL-001", "src/guard.py:1")),
        "fixtures": {"fixtures": [FIXTURE]},
        "expect": {"exit": 0, "selected": [], "uncovered": []},
    },
    {
        "name": "fixture-artifact-change",
        "base": {"src/a.py": "x = 1\n"},
        "head": {"src/a.py": "x = 2\n"},
        "fixtures": {"fixtures": [FIXTURE]},
        "expect": {"exit": 0, "selected": ["MUT-001"], "uncovered": []},
    },
    {
        "name": "enforced-at-path-change",
        "base": {"src/guard.py": "def guard():\n    return True\n", "src/a.py": "x = 1\n"},
        "head": {"src/guard.py": "def guard():\n    return False\n"},
        "cells": _registry(_cell("CELL-002", "src/guard.py:1 - the guard")),
        "fixtures": {"fixtures": [{"id": "MUT-002", "cell": "CELL-002",
                                   "artifact": "src/a.py"}]},
        "expect": {"exit": 0, "selected": ["MUT-002"], "uncovered": []},
    },
    {
        "name": "detector-artifact-change",
        "base": {"tests/test_guard.py": "def test_guard():\n    assert True\n",
                 "src/a.py": "x = 1\n"},
        "head": {"tests/test_guard.py": "def test_guard():\n    assert False\n"},
        "cells": _registry(_cell("CELL-003", detectors=[{
            "id": "D-GUARD", "kind": "test", "status": "tested",
            "artifact": "tests/test_guard.py",
            "mutation_fixture": "mutations.yaml#MUT-003"}])),
        "fixtures": {"fixtures": [{"id": "MUT-003", "cell": "CELL-003",
                                   "artifact": "src/a.py"}]},
        "expect": {"exit": 0, "selected": ["MUT-003"], "uncovered": []},
    },
    {
        "name": "cell-registry-change",
        "base": {"src/a.py": "x = 1\n"},
        "head": {"src/note.md": "registry edited\n"},
        "base_cells": _registry(_cell("CELL-004", "src/guard.py:1")),
        "cells": _registry(dict(_cell("CELL-004", "src/guard.py:1"),
                                title="A different synthetic invariant.")),
        "fixtures": {"fixtures": [{"id": "MUT-004", "cell": "CELL-004",
                                   "artifact": "src/a.py"}]},
        "expect": {"exit": 0, "selected": ["MUT-004"],
                   "changed_cells": ["CELL-004"], "uncovered": []},
    },
    {
        "name": "unrelated-file-no-selection",
        "base": {"src/a.py": "x = 1\n"},
        "head": {"README.md": "unrelated\n"},
        "fixtures": {"fixtures": [FIXTURE]},
        "expect": {"exit": 0, "selected": [], "uncovered": []},
    },
    {
        "name": "uncovered-changed-cell-fails",
        "base": {"src/guard.py": "def guard():\n    return True\n",
                 "src/a.py": "x = 1\n"},
        "head": {"src/guard.py": "def guard():\n    return False\n"},
        "cells": _registry(_cell("CELL-005", "src/guard.py:1")),
        "fixtures": {"fixtures": [FIXTURE]},
        "args": ["--require-fixtures"],
        "expect": {"exit": 1, "selected": [], "uncovered": ["CELL-005"]},
    },
    {
        "name": "exempt-cell-does-not-fail",
        "base": {"src/guard.py": "def guard():\n    return True\n",
                 "src/a.py": "x = 1\n"},
        "head": {"src/guard.py": "def guard():\n    return False\n"},
        "cells": _registry(_cell("CELL-006", "src/guard.py:1", detectors=[{
            "id": "D-PLATFORM", "kind": "test", "status": "tested",
            "artifact": "tests/test_guard.py",
            "mutation_exemption": "platform semantics"}])) ,
        "fixtures": {"fixtures": [FIXTURE]},
        "args": ["--require-fixtures"],
        "expect": {"exit": 0, "selected": [], "uncovered": []},
    },
    {
        "name": "open-changed-cell-does-not-fail",
        "base": {"src/guard.py": "def guard():\n    return True\n",
                 "src/a.py": "x = 1\n"},
        "head": {"src/guard.py": "def guard():\n    return False\n"},
        "cells": _registry(dict(_cell("CELL-007", "src/guard.py:1"),
                                coverage_status="open")),
        "fixtures": {"fixtures": [FIXTURE]},
        "args": ["--require-fixtures"],
        "expect": {"exit": 0, "selected": [], "uncovered": []},
    },
    {
        "name": "all-selects-every-fixture",
        "base": {"src/a.py": "x = 1\n"},
        "head": {"src/note.md": "nothing relevant\n"},
        "fixtures": {"fixtures": [
            FIXTURE,
            {"id": "MUT-009", "cell": "CELL-009", "artifact": "src/b.py"}]},
        "args": ["--all"],
        "expect": {"exit": 0, "selected": ["MUT-001", "MUT-009"],
                   "uncovered": []},
    },
    {
        "name": "unknown-base-exits-2",
        "base": {"src/a.py": "x = 1\n"},
        "head": {},
        "fixtures": {"fixtures": [FIXTURE]},
        "override_base": "no-such-ref",
        "expect": {"exit": 2},
    },
    {
        "name": "missing-fixtures-exits-2",
        "base": {"src/a.py": "x = 1\n"},
        "head": {},
        "fixtures": None,
        "expect": {"exit": 2},
    },
    {
        "name": "deleted-artifact-is-selected",
        "base": {"src/a.py": "x = 1\n"},
        "head": {"src/a.py": None},
        "fixtures": {"fixtures": [FIXTURE]},
        "expect": {"exit": 0, "selected": ["MUT-001"], "uncovered": []},
    },
]


def _dotted(data, key):
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return "<missing>"
    return node


def run(scenario, tool):
    problems = []
    td = tempfile.mkdtemp(prefix="mutation-plan-eval-")
    try:
        _init(td)
        for rel, content in scenario.get("base", {}).items():
            _write(td, rel, content)
        _commit(td, "base")

        for rel, content in scenario.get("head", {}).items():
            _write(td, rel, content)
        if scenario.get("head"):
            _commit(td, "head")
        base = scenario.get("override_base") or _git(td, "rev-parse", "HEAD~1" if
                                                     scenario.get("head") else "HEAD").strip()

        if scenario.get("fixtures") is not None:
            _write(td, "fixtures.yaml", scenario["fixtures"])
        if scenario.get("base_cells") is not None:
            _write(td, "cells-base.yaml", scenario["base_cells"])
        if scenario.get("cells") is not None:
            _write(td, "cells.yaml", scenario["cells"])

        args = ["--repo", td, "--base", base, "--head", "HEAD",
                "--fixtures", os.path.join(td, "fixtures.yaml")]
        if scenario.get("cells") is not None:
            args += ["--cells", os.path.join(td, "cells.yaml")]
        if scenario.get("base_cells") is not None:
            args += ["--cells-base", os.path.join(td, "cells-base.yaml")]
        args += scenario.get("args") or []
        json_path = os.path.join(td, "plan.json")
        if scenario.get("expect", {}).get("changed_cells") is not None \
                or scenario.get("expect", {}).get("selected") is not None:
            args += ["--json", json_path]

        proc = subprocess.run([sys.executable, tool] + args, cwd=td,
                              capture_output=True, text=True, timeout=60)
        expect = scenario.get("expect") or {}
        if proc.returncode != expect.get("exit"):
            problems.append("exit: expected %s, got %d (%s)"
                            % (expect.get("exit"), proc.returncode,
                               proc.stderr.strip()[:200]))
        selected = []
        gaps = []
        for line in proc.stdout.splitlines():
            if line.startswith("PLAN  "):
                parts = line.split()
                if len(parts) >= 3 and parts[1] != "no":
                    selected.append(parts[1])
            elif line.startswith("GAP   "):
                parts = line.split()
                if len(parts) >= 2:
                    gaps.append(parts[1])
        if "selected" in expect and sorted(selected) != sorted(expect["selected"]):
            problems.append("selected: expected %s, got %s"
                            % (expect["selected"], selected))
        if "uncovered" in expect and sorted(gaps) != sorted(expect["uncovered"]):
            problems.append("uncovered: expected %s, got %s"
                            % (expect["uncovered"], gaps))
        if json_path and os.path.exists(json_path):
            report = json.load(open(json_path, encoding="utf-8"))
            for key, wanted in (expect.get("json") or {}).items():
                got = _dotted(report, key)
                if got != wanted:
                    problems.append("json %s: expected %r, got %r"
                                    % (key, wanted, got))
            if "changed_cells" in expect:
                got = report.get("changed_cells") or []
                if got != expect["changed_cells"]:
                    problems.append("changed_cells: expected %s, got %s"
                                    % (expect["changed_cells"], got))
        elif expect.get("changed_cells") is not None:
            problems.append("plan JSON was not written")
    finally:
        subprocess.run(["rm", "-rf", td])
    return scenario["name"], problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "mutation_plan.py"))
    args = ap.parse_args()
    failed = 0
    for scenario in SCENARIOS:
        name, problems = run(scenario, args.tool)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % name)
    print("%d/%d mutation-plan eval cases passed"
          % (len(SCENARIOS) - failed, len(SCENARIOS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
