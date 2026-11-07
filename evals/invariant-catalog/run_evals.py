#!/usr/bin/env python3
"""Adversarial eval runner for tools/invariant_catalog.py (V2-21).

Each case starts from a synthetic, valid catalogue with two invariants in each
of the five categories, applies one defect, and checks the expected INV check
fires. The fixtures are synthetic and marked as such; they prove the catalogue
checks fail closed on the named defects, not that any real invariant holds.

Usage:
    python3 evals/invariant-catalog/run_evals.py [--tool PATH]
"""

import argparse
import copy
import json
import os
import re
import shutil
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
SCHEMA = os.path.join(REPO, "schemas", "invariant-catalog.schema.json")
FINDING_RE = re.compile(r"^\[(INV\d)\]\s+(error|warning|info)\b")
PREFIX = {"input-validation": "IV", "authn-session": "AS", "secrets": "SE",
          "lifecycle": "LC", "transactions": "TX"}
RULES = ["rule-input", "rule-authn", "rule-secret", "rule-life", "rule-tx"]


def _invariant(iid, category, rule, cells, taxonomy="security", mode="deny"):
    return {
        "id": iid,
        "category": category,
        "statement": "A synthetic invariant statement long enough to be checked.",
        "enforcement": "One synthetic choke point every path crosses.",
        "taxonomy_class": taxonomy,
        "failure_class": "synthetic-failure",
        "failure_mode": mode,
        "entry_points": ["http"],
        "choke_point_rule": rule,
        "seed_cells": list(cells),
        "oracle": "A synthetic observation that distinguishes a violation.",
        "violation_response": "The synthetic operation is denied before any write.",
        "evidence_kind": "test",
        "negative_test": "A synthetic negative test that must fail when removed.",
        "status": "open",
        "bypasses": [
            "A synthetic alternate path skips the shared check.",
            "A synthetic cache returns a stale decision.",
        ],
        "limitations": "Synthetic fixture: no detector and no recorded run exist.",
    }


def _base():
    categories = {}
    for name in PREFIX:
        categories[name] = {
            "title": "Synthetic category %s" % name,
            "taxonomy_class": "security" if name != "transactions" else "correctness",
            "failure_class": "synthetic-failure",
            "description": "A synthetic category description long enough.",
        }
    invariants = []
    cells = ["CELL-001", "CELL-002", "CELL-003"]
    for index, name in enumerate(PREFIX, 1):
        rule = RULES[index - 1]
        invariants.append(_invariant("INV-%s-001" % PREFIX[name], name, rule,
                                     [cells[(index - 1) % 3]]))
        invariants.append(_invariant("INV-%s-002" % PREFIX[name], name, rule,
                                     [cells[index % 3]]))
    return {
        "version": 1,
        "generated": "2026-11-07",
        "categories": categories,
        "invariants": invariants,
    }


def _cells():
    return {"cells": [{"id": "CELL-%03d" % i} for i in range(1, 4)]}


def _rules():
    return {"signals": [], "rules": [{"id": rule} for rule in RULES]}


def _entry(catalog, iid):
    for entry in catalog["invariants"]:
        if entry["id"] == iid:
            return entry
    raise KeyError(iid)


SCENARIOS = [
    {"name": "valid-control", "edit": lambda c: None,
     "expect": {"exit": 0, "errors": [], "json": {"invariants": 10}}},
    {"name": "missing-category",
     "edit": lambda c: c["categories"].pop("secrets"),
     "expect": {"exit": 1, "errors": ["INV1"]}},
    {"name": "category-too-few",
     "edit": lambda c: c["invariants"].remove(_entry(c, "INV-SE-002")),
     "expect": {"exit": 1, "errors": ["INV1"]}},
    {"name": "duplicate-id",
     "edit": lambda c: _entry(c, "INV-SE-002").__setitem__("id", "INV-SE-001"),
     "expect": {"exit": 1, "errors": ["INV2"]}},
    {"name": "unknown-seed-cell",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__("seed_cells",
                                                           ["CELL-999"]),
     "expect": {"exit": 1, "errors": ["INV3"]}},
    {"name": "unknown-rule",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__(
         "choke_point_rule", "no-such-rule"),
     "expect": {"exit": 1, "errors": ["INV3"]}},
    {"name": "invalid-taxonomy-class",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__(
         "taxonomy_class", "other"),
     "expect": {"exit": 1, "errors": ["INV2"]}},
    {"name": "unknown-failure-mode",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__(
         "failure_mode", "other"),
     "expect": {"exit": 1, "errors": ["INV2"]}},
    {"name": "one-bypass-only",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__(
         "bypasses", ["Only one synthetic bypass is not enough."]),
     "expect": {"exit": 1, "errors": ["INV2"]}},
    {"name": "id-prefix-mismatch",
     "edit": lambda c: _entry(c, "INV-AS-001").__setitem__(
         "id", "INV-IV-020"),
     "expect": {"exit": 1, "errors": ["INV2"]}},
    {"name": "unmapped-seed-cell",
     "edit": lambda c: None,
     "cells": {"cells": [{"id": "CELL-%03d" % i} for i in range(1, 6)]},
     "expect": {"exit": 1, "errors": ["INV5"]}},
    {"name": "referenced-and-out-of-scope",
     "edit": lambda c: c.__setitem__("out_of_scope", [
         {"cell": "CELL-001", "reason": "Synthetic scope conflict."}]),
     "expect": {"exit": 1, "errors": ["INV3"]}},
    {"name": "non-open-without-evidence",
     "edit": lambda c: _entry(c, "INV-SE-001").__setitem__("status", "tested"),
     "expect": {"exit": 1, "errors": ["INV4"]}},
    {"name": "out-of-scope-covers-seed-cell",
     "edit": lambda c: c.__setitem__("out_of_scope", [
         {"cell": "CELL-004", "reason": "Synthetic out-of-scope cell."}]),
     "cells": {"cells": [{"id": "CELL-%03d" % i} for i in range(1, 5)]},
     "expect": {"exit": 0, "errors": []}},
    {"name": "missing-catalog-exits-2", "skip_catalog": True,
     "edit": lambda c: None, "expect": {"exit": 2}},
]


def _dotted(data, key):
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return "<missing>"
    return node


def run(scenario, tool):
    problems = []
    td = tempfile.mkdtemp(prefix="invariant-catalog-eval-")
    try:
        catalog = copy.deepcopy(_base())
        scenario["edit"](catalog)
        with open(os.path.join(td, "catalog.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(catalog, f, allow_unicode=True, sort_keys=False)
        cells = scenario.get("cells") or _cells()
        with open(os.path.join(td, "cells.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cells, f, allow_unicode=True, sort_keys=False)
        with open(os.path.join(td, "rules.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(_rules(), f, allow_unicode=True, sort_keys=False)

        catalog_path = (os.path.join(td, "missing.yaml")
                        if scenario.get("skip_catalog")
                        else os.path.join(td, "catalog.yaml"))
        json_path = os.path.join(td, "report.json")
        args = ["--catalog", catalog_path,
                "--cells", os.path.join(td, "cells.yaml"),
                "--rules", os.path.join(td, "rules.yaml"),
                "--schema", SCHEMA, "--json", json_path]
        proc = subprocess.run([sys.executable, tool] + args, cwd=td,
                              capture_output=True, text=True, timeout=60)
        expect = scenario.get("expect") or {}
        if proc.returncode != expect.get("exit"):
            problems.append("exit: expected %s, got %d (%s)"
                            % (expect.get("exit"), proc.returncode,
                               proc.stderr.strip()[:200]))
        seen = {}
        for line in proc.stdout.splitlines():
            match = FINDING_RE.match(line)
            if match and match.group(2) == "error":
                seen[match.group(1)] = seen.get(match.group(1), 0) + 1
        if "errors" in expect:
            got = sorted(seen)
            if got != sorted(expect["errors"]):
                problems.append("errors: expected %s, got %s"
                                % (expect["errors"], got))
        if json_path and os.path.exists(json_path):
            report = json.load(open(json_path, encoding="utf-8"))
            for key, wanted in (expect.get("json") or {}).items():
                got = _dotted(report, key)
                if got != wanted:
                    problems.append("json %s: expected %r, got %r"
                                    % (key, wanted, got))
        elif expect.get("json") is not None:
            problems.append("JSON report was not written")
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return scenario["name"], problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "invariant_catalog.py"))
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
    print("%d/%d invariant-catalog eval cases passed"
          % (len(SCENARIOS) - failed, len(SCENARIOS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
