#!/usr/bin/env python3
"""Select mutation fixtures for the cells a diff touched (V2-11).

The mutation runners can already run one fixture (`--only`), but a CI job that
runs every fixture pays for cells the change never touched. This tool maps a
target-repository diff to cell IDs, then to fixture IDs, and prints the plan.
It does not run anything: `run_mutations.py --plan plan.json` executes it.

Mapping is deliberately file-level and conservative:

  1. a fixture whose mutated `artifact` changed is selected (`fixture-artifact`);
  2. a cell whose registry entry changed is selected (`cell-changed`);
  3. a cell whose `enforced_at` declaration names a changed path is selected
     (`enforced-at`);
  4. a cell whose detector `artifact` is a changed path is selected
     (`detector-artifact`).

A changed file that maps to no cell is reported, not guessed. A changed cell
with no fixture is reported as `uncovered` and, with `--require-fixtures`,
fails the plan: a changed enforcement site must have a negative control or a
documented exemption, otherwise CI would give a green run for an untested
change.

Exit codes: 0 plan produced, 1 a changed cell has no fixture under
`--require-fixtures`, 2 tool, git or input error.

Usage:
    python3 tools/mutation_plan.py \
        --repo ../rbac_pg --base v1.3.1 --head HEAD \
        --fixtures spec/pilots/rbac_pg/mutations/mutations.yaml \
        --cells spec/pilots/rbac_pg/cells.yaml \
        --cells-base old-cells.yaml \
        --json /tmp/opencode/plan.json

`--base` should be the merge base of the PR, not the base branch tip; the
caller resolves it (`git merge-base origin/main HEAD`). The tool compares
`base..head` and never checks out or modifies the target repository.
"""

import argparse
import json
import os
import re
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

# A path-looking token in an `enforced_at` sentence. The lookbehind keeps
# `https://host/file.py` and `name.py` inside a word from becoming a path.
PATH_RE = re.compile(
    r"(?<![:/A-Za-z0-9_.-])"
    r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
    r"\.(?:py|rs|sql|go|js|jsx|ts|tsx|java|kt|kts|rb|cs|c|cc|cpp|h|hpp|sh|"
    r"yaml|yml|toml|json))"
    r"(?::[0-9]+)?")


def run_git(repo, argv):
    proc = subprocess.run(["git", "-C", repo] + argv, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise RuntimeError("git %s failed: %s"
                           % (" ".join(argv), proc.stderr.strip()))
    return proc.stdout


def changed_files(repo, base, head):
    out = run_git(repo, ["diff", "--name-status", "--find-renames",
                         "%s..%s" % (base, head)])
    items = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            items.append({"status": status, "path": parts[2],
                          "old_path": parts[1]})
        elif len(parts) >= 2:
            items.append({"status": status, "path": parts[1]})
    return items


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      default=str)


def changed_cells(current, previous):
    """Cell IDs added or edited between two registry files."""
    if not previous:
        return []
    before = {c["id"]: c for c in previous.get("cells") or [] if "id" in c}
    changed = []
    for cell in current.get("cells") or []:
        cid = cell.get("id")
        if not cid:
            continue
        if cid not in before or canonical(cell) != canonical(before[cid]):
            changed.append(cid)
    return changed


def is_repo_path(value):
    return (isinstance(value, str) and value
            and "://" not in value and not value.startswith(("/", "~")))


def declared_paths(cell):
    """Paths a cell names in `enforced_at`, plus detector artifacts."""
    paths = set()
    enforced = cell.get("enforced_at")
    if isinstance(enforced, str):
        for match in PATH_RE.finditer(enforced):
            paths.add(match.group(1).lstrip("./"))
    for detector in cell.get("detectors") or []:
        artifact = detector.get("artifact")
        if is_repo_path(artifact):
            paths.add(artifact.lstrip("./"))
    return paths


def package(doc, key):
    value = doc.get(key) if isinstance(doc, dict) else None
    if isinstance(value, list):
        return value
    return []


def plan(args):
    fixtures_doc = load_yaml(args.fixtures)
    fixtures = package(fixtures_doc, "fixtures")
    if not fixtures:
        raise RuntimeError("no fixtures in %s" % args.fixtures)

    cells_doc = load_yaml(args.cells) if args.cells else {}
    cells = {c["id"]: c for c in package(cells_doc, "cells") if "id" in c}

    previous_cells = load_yaml(args.cells_base) if args.cells_base else {}
    touched_cells = changed_cells(cells_doc, previous_cells)

    if args.all:
        files = []
        selected = [{"fixture": fx["id"], "cell": fx.get("cell"),
                     "artifact": fx.get("artifact"),
                     "reason": "all"} for fx in fixtures]
        return {"format": "dev-sec-skills/mutation-plan/v1",
                "repo": args.repo, "base": args.base, "head": args.head,
                "changed_files": files, "changed_cells": [],
                "selected": selected, "unselected": [], "uncovered": [],
                "changed_files_without_cell": []}

    files = changed_files(args.repo, args.base, args.head)
    changed = set()
    for item in files:
        changed.add(item["path"].lstrip("./"))
        old = item.get("old_path")
        if old:
            changed.add(old.lstrip("./"))

    touched = set(touched_cells)
    for cid, cell in cells.items():
        if declared_paths(cell) & changed:
            touched.add(cid)

    fixture_by_cell = {}
    for fx in fixtures:
        fixture_by_cell.setdefault(fx.get("cell"), []).append(fx)

    selected = []
    unselected = []
    for fx in fixtures:
        reasons = []
        if fx.get("artifact") in changed:
            reasons.append("fixture-artifact")
        if fx.get("cell") in touched_cells:
            reasons.append("cell-changed")
        cell = cells.get(fx.get("cell"))
        if cell is not None:
            enforced_paths = set()
            enforced = cell.get("enforced_at")
            if isinstance(enforced, str):
                enforced_paths = {m.group(1).lstrip("./")
                                  for m in PATH_RE.finditer(enforced)}
            if enforced_paths & changed:
                reasons.append("enforced-at")
            detector_paths = {
                d.get("artifact", "").lstrip("./")
                for d in cell.get("detectors") or []
                if is_repo_path(d.get("artifact"))}
            if detector_paths & changed:
                reasons.append("detector-artifact")
        if reasons:
            selected.append({"fixture": fx["id"], "cell": fx.get("cell"),
                             "artifact": fx.get("artifact"),
                             "reason": reasons[0], "reasons": reasons})
        else:
            unselected.append({"fixture": fx["id"], "cell": fx.get("cell")})

    # A changed cell with no fixture is a gap, not a quiet pass. A detector
    # with a mutation_exemption is covered by a documented argument instead.
    uncovered = []
    for cid in sorted(touched):
        cell = cells.get(cid)
        if cell is None:
            continue
        has_fixture = bool(fixture_by_cell.get(cid))
        detectors = cell.get("detectors") or []
        exempt = bool(detectors) and all(
            d.get("mutation_exemption") or d.get("kind") in
            ("review", "proof", "rule")
            for d in detectors)
        if not has_fixture and not exempt \
                and cell.get("coverage_status") != "open":
            uncovered.append({"cell": cid,
                              "reason": "changed cell has no fixture"})

    mapped_paths = set()
    for cell in cells.values():
        mapped_paths |= declared_paths(cell)
    for fx in fixtures:
        if is_repo_path(fx.get("artifact")):
            mapped_paths.add(fx["artifact"].lstrip("./"))
    unmapped_files = sorted(p for p in changed
                            if p not in mapped_paths
                            and not p.endswith((".md", ".txt")))

    return {
        "format": "dev-sec-skills/mutation-plan/v1",
        "repo": args.repo,
        "base": args.base,
        "head": args.head,
        "changed_files": files,
        "changed_cells": sorted(touched),
        "selected": selected,
        "unselected": unselected,
        "uncovered": uncovered,
        "changed_files_without_cell": unmapped_files,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True,
                    help="target git repository (read-only)")
    ap.add_argument("--base", required=True,
                    help="merge base or base commit")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--fixtures", required=True,
                    help="mutations.yaml with fixture id/artifact/cell")
    ap.add_argument("--cells", default=None,
                    help="current cell registry (for enforced_at/detector paths)")
    ap.add_argument("--cells-base", default=None,
                    help="previous cell registry; cells added or edited are selected")
    ap.add_argument("--all", action="store_true",
                    help="select every fixture, for a scheduled full run")
    ap.add_argument("--require-fixtures", action="store_true",
                    help="exit 1 when a changed cell has no fixture and no exemption")
    ap.add_argument("--json", default=None, help="write the plan as JSON")
    args = ap.parse_args()

    if not os.path.isdir(args.repo):
        print("error: repository not found: %s" % args.repo, file=sys.stderr)
        return 2
    for label, path in (("fixtures", args.fixtures), ("cells", args.cells),
                        ("cells-base", args.cells_base)):
        if path and not os.path.exists(path):
            print("error: %s file not found: %s" % (label, path),
                  file=sys.stderr)
            return 2

    try:
        result = plan(args)
    except (RuntimeError, OSError, yaml.YAMLError, KeyError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    for item in result["selected"]:
        print("PLAN  %-10s %-10s %-20s %s"
              % (item["fixture"], item["cell"], item["reason"],
                 item["artifact"]))
    if not result["selected"]:
        print("PLAN  no fixtures selected: the diff touches no fixture, cell, "
              "declared choke point or detector artifact")
    for item in result["uncovered"]:
        print("GAP   %-10s %s" % (item["cell"], item["reason"]))
    if result["changed_files_without_cell"]:
        print("INFO  %d changed file(s) map to no cell"
              % len(result["changed_files_without_cell"]))
    print("plan: %d/%d fixture(s) selected, %d changed file(s), "
          "%d changed cell(s), %d uncovered"
          % (len(result["selected"]), len(result["unselected"])
             + len(result["selected"]), len(result["changed_files"]),
             len(result["changed_cells"]), len(result["uncovered"])))

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    if args.require_fixtures and result["uncovered"]:
        print("error: %d changed cell(s) have no fixture or documented "
              "exemption" % len(result["uncovered"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
