#!/usr/bin/env python3
"""Validate the general-code invariant catalogue (V2-21).

The catalogue is design knowledge, not evidence. This tool checks that every
entry is falsifiable and traceable:

  INV1 categories  exactly the five V2-21 categories, each with at least two
                   invariants and a class/failure pair;
  INV2 shape       required fields, unique IDs, allowed enums, at least two
                   bypasses, no `other` escape hatch, IDs match their category;
  INV3 references  category, seed cell and choke-point rule exist; a seed cell is
  INV4 evidence    either referenced by an invariant or listed in out_of_scope,
                   and a non-open entry names an existing evidence artifact;
  INV5 coverage    every category is populated, every rule a catalogue entry
                   names exists, and unused rules are reported, not hidden.

A green run means the catalogue is internally consistent. It does not mean any
invariant holds: all entries start `open`, and the negative test is a
specification until a detector cites it.

Exit codes: 0 no errors, 1 errors, 2 tool or input error.

Usage:
    python3 tools/invariant_catalog.py \
        --catalog spec/invariants/catalog.yaml \
        --cells spec/conveyor/cells.seed.yaml \
        --rules spec/choke-points/rules.yaml \
        [--schema spec/conveyor/cell-registry.schema.json] \
        [--json spec/invariants/2026-11-07-coverage.json]
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

CATEGORIES = ("input-validation", "authn-session", "secrets", "lifecycle",
              "transactions")
PREFIX = {"input-validation": "IV", "authn-session": "AS", "secrets": "SE",
          "lifecycle": "LC", "transactions": "TX"}
TAXONOMY = {"security", "correctness", "maintainability", "performance"}
FAILURE_MODES = {"deny", "abort", "rollback", "safe-degrade", "detect"}
STATUSES = {"proven", "model-checked", "tested", "static-refinement",
            "reviewed", "open"}
EVIDENCE_KINDS = {"test", "runtime-enforcement", "review", "tool-output"}
REQUIRED = (
    "id", "category", "statement", "enforcement", "taxonomy_class",
    "failure_class", "failure_mode", "entry_points", "choke_point_rule",
    "seed_cells", "oracle", "violation_response", "evidence_kind",
    "negative_test", "status", "bypasses", "limitations")
CATEGORY_REQUIRED = ("title", "taxonomy_class", "failure_class", "description")
ID_RE = re.compile(r"^INV-([A-Z]{2})-([0-9]{3})$")
CELL_RE = re.compile(r"^CELL-[0-9]{3,}$")


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, level, check, message):
        self.rows.append({"level": level, "check": check, "message": message})

    def error(self, check, message):
        self.add("error", check, message)

    def warning(self, check, message):
        self.add("warning", check, message)

    def info(self, check, message):
        self.add("info", check, message)

    @property
    def errors(self):
        return [row for row in self.rows if row["level"] == "error"]


def read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def schema_enums(schema):
    taxonomy = set(TAXONOMY)
    modes = set(FAILURE_MODES)
    classes = list(CATEGORIES)
    try:
        cell = schema["definitions"]["cell"]["properties"]
        taxonomy = set(cell["taxonomy_class"]["enum"])
        modes = set(cell["failure_mode"]["enum"])
    except (KeyError, TypeError):
        pass
    try:
        names = set(schema["definitions"]["invariant"]["properties"]["category"]["enum"])
        classes = list(CATEGORIES) + sorted(names - set(CATEGORIES))
    except (KeyError, TypeError):
        pass
    return taxonomy, modes, classes


def validate(catalog, cells_doc, rules_doc, schema_doc):
    report = Report()
    taxonomy, failure_modes, categories_enum = schema_enums(schema_doc or {})

    categories = catalog.get("categories") or {}
    if not isinstance(categories, dict):
        report.error("INV1", "categories must be a mapping")
        categories = {}
    missing = [c for c in categories_enum if c not in categories]
    extra = [c for c in categories if c not in categories_enum]
    for name in missing:
        report.error("INV1", "missing category %r" % name)
    for name in extra:
        report.error("INV1", "unknown category %r" % name)

    seed_cells = {c.get("id") for c in (cells_doc.get("cells") or [])
                  if c.get("id")}
    rule_ids = {r.get("id") for r in (rules_doc.get("rules") or [])
                if r.get("id")}

    invariants = catalog.get("invariants") or []
    if not isinstance(invariants, list) or not invariants:
        report.error("INV2", "invariants must be a non-empty list")
        invariants = []

    seen = set()
    by_category = {name: [] for name in categories_enum}
    cell_refs = {}
    rules_used = set()

    for entry in invariants:
        if not isinstance(entry, dict):
            report.error("INV2", "an invariant entry is not a mapping")
            continue
        iid = entry.get("id", "<missing>")
        for field in REQUIRED:
            if field not in entry or entry[field] in ("", None, []):
                report.error("INV2", "%s: missing or empty %r" % (iid, field))
        match = ID_RE.match(str(entry.get("id", "")))
        if not match:
            report.error("INV2", "%s: id does not match INV-XX-NNN" % iid)
        if iid in seen:
            report.error("INV2", "%s: duplicate id" % iid)
        seen.add(iid)

        category = entry.get("category")
        if category not in categories_enum:
            report.error("INV2", "%s: unknown category %r" % (iid, category))
        else:
            by_category.setdefault(category, []).append(iid)
            if match and match.group(1) != PREFIX[category]:
                report.error("INV2", "%s: prefix %s does not match category %s"
                             % (iid, match.group(1), category))

        if entry.get("taxonomy_class") not in taxonomy:
            report.error("INV2", "%s: taxonomy_class %r is not in the cell schema"
                         % (iid, entry.get("taxonomy_class")))
        if entry.get("failure_mode") not in failure_modes:
            report.error("INV2", "%s: failure_mode %r is not in the cell schema"
                         % (iid, entry.get("failure_mode")))
        if entry.get("evidence_kind") not in EVIDENCE_KINDS:
            report.error("INV2", "%s: unknown evidence_kind %r"
                         % (iid, entry.get("evidence_kind")))
        if entry.get("status") not in STATUSES:
            report.error("INV2", "%s: unknown status %r"
                         % (iid, entry.get("status")))
        bypasses = entry.get("bypasses") or []
        if len(bypasses) < 2:
            report.error("INV2", "%s: needs at least two bypasses" % iid)
        for point in entry.get("entry_points") or []:
            if not isinstance(point, str) or not point:
                report.error("INV2", "%s: entry_points must be non-empty strings"
                             % iid)

        rule = entry.get("choke_point_rule")
        if rule not in rule_ids:
            report.error("INV3", "%s: choke_point_rule %r is not in %s"
                         % (iid, rule, "rules.yaml"))
        else:
            rules_used.add(rule)

        refs = entry.get("seed_cells") or []
        if not refs:
            report.error("INV3", "%s: seed_cells is empty" % iid)
        for cell in refs:
            if not CELL_RE.match(str(cell)):
                report.error("INV3", "%s: bad seed cell id %r" % (iid, cell))
            elif cell not in seed_cells:
                report.error("INV3", "%s: seed cell %r does not exist" % (iid, cell))
            else:
                cell_refs.setdefault(cell, []).append(iid)

        if entry.get("status") not in ("open", None):
            evidence = entry.get("evidence_path")
            if not evidence:
                report.error("INV4", "%s: status %r needs evidence_path"
                             % (iid, entry.get("status")))
            elif not os.path.exists(evidence):
                report.error("INV4", "%s: evidence_path not found: %s"
                             % (iid, evidence))

    for category in categories_enum:
        count = len(by_category.get(category) or [])
        if count < 2:
            report.error("INV1", "category %r has %d invariant(s); need at least 2"
                         % (category, count))
        spec = categories.get(category)
        if not isinstance(spec, dict):
            continue
        for field in CATEGORY_REQUIRED:
            if not spec.get(field):
                report.error("INV1", "category %r: missing %r" % (category, field))
        if spec.get("taxonomy_class") not in taxonomy:
            report.error("INV1", "category %r: taxonomy_class %r not in schema"
                         % (category, spec.get("taxonomy_class")))

    out_of_scope = {}
    for item in catalog.get("out_of_scope") or []:
        cell = item.get("cell")
        reason = item.get("reason")
        if not cell or not reason:
            report.error("INV3", "out_of_scope entry needs cell and reason")
            continue
        if not CELL_RE.match(str(cell)):
            report.error("INV3", "out_of_scope: bad cell id %r" % cell)
        if cell not in seed_cells:
            report.error("INV3", "out_of_scope: cell %r does not exist" % cell)
        if cell in out_of_scope:
            report.error("INV3", "out_of_scope: duplicate cell %r" % cell)
        out_of_scope[cell] = reason

    overlap = sorted(set(cell_refs) & set(out_of_scope))
    for cell in overlap:
        report.error("INV3", "cell %r is both referenced and out_of_scope" % cell)
    for cell in sorted(seed_cells - set(cell_refs) - set(out_of_scope)):
        report.error("INV5", "seed cell %r is neither referenced nor out_of_scope"
                     % cell)

    unused_rules = sorted(rule_ids - rules_used)
    for rule in unused_rules:
        report.info("INV5", "rule %r has no catalogue entry" % rule)

    for row in report.rows:
        prefix = "[%s] %-7s" % (row["check"], row["level"])
        print("%s %s" % (prefix, row["message"]))

    summary = {
        "generated": date.today().isoformat(),
        "catalog_generated": str(catalog.get("generated")),
        "categories": {
            name: {
                "count": len(by_category.get(name) or []),
                "invariants": by_category.get(name) or [],
            } for name in categories_enum
        },
        "invariants": len(invariants),
        "status": _counts(entry.get("status") for entry in invariants
                          if isinstance(entry, dict)),
        "seed_cells": {
            "total": len(seed_cells),
            "referenced": len(cell_refs),
            "out_of_scope": len(out_of_scope),
            "unmapped": sorted(seed_cells - set(cell_refs) - set(out_of_scope)),
        },
        "rules": {
            "total": len(rule_ids),
            "used": sorted(rules_used),
            "unused": unused_rules,
        },
        "matrix": [
            {"cell": cell,
             "invariants": sorted(invariants_for)}
            for cell, invariants_for in sorted(cell_refs.items())
        ],
        "out_of_scope": [
            {"cell": cell, "reason": reason}
            for cell, reason in sorted(out_of_scope.items())
        ],
        "errors": len(report.errors),
        "warnings": len([row for row in report.rows
                         if row["level"] == "warning"]),
    }
    print("catalogue: %d invariants across %d categories; %d/%d seed cells "
          "referenced, %d out_of_scope, %d rule(s) used of %d"
          % (len(invariants), len([c for c in categories_enum
                                   if by_category.get(c)]),
             len(cell_refs), len(seed_cells), len(out_of_scope),
             len(rules_used), len(rule_ids)))
    return summary, report


def _counts(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--cells", default=os.path.join(
        here, "spec", "conveyor", "cells.seed.yaml"))
    ap.add_argument("--rules", default=os.path.join(
        here, "spec", "choke-points", "rules.yaml"))
    ap.add_argument("--schema", default=os.path.join(
        here, "schemas", "invariant-catalog.schema.json"))
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    for label, path in (("catalog", args.catalog), ("cells", args.cells),
                        ("rules", args.rules)):
        if not os.path.exists(path):
            print("error: %s file not found: %s" % (label, path), file=sys.stderr)
            return 2

    try:
        catalog = read_yaml(args.catalog)
        cells_doc = read_yaml(args.cells)
        rules_doc = read_yaml(args.rules)
        schema_doc = read_yaml(args.schema) if os.path.exists(args.schema) else {}
    except (OSError, yaml.YAMLError) as exc:
        print("error: cannot read input: %s" % exc, file=sys.stderr)
        return 2

    # The JSON schema is documentation plus the enum source; the hand checks
    # below carry the messages. Loading it is optional so the tool still works
    # when vendored without the schema.
    summary, report = validate(catalog, cells_doc, rules_doc, schema_doc)
    # Every number this run produced is anchored to the exact inputs: the
    # hash says whether two runs judged against the same cells, not "same
    # file name".
    summary["inputs"] = {
        "catalog": {"path": args.catalog, "sha256": sha256_of(args.catalog)},
        "cells": {"path": args.cells, "sha256": sha256_of(args.cells)},
        "rules": {"path": args.rules, "sha256": sha256_of(args.rules)},
    }
    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print("inputs: catalog %s, cells %s, rules %s"
          % (sha256_of(args.catalog)[:12], sha256_of(args.cells)[:12],
             sha256_of(args.rules)[:12]))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
