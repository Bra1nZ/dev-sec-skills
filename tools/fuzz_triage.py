#!/usr/bin/env python3
"""Fuzz triage gate — every finding becomes a cell, a detector and a fixture.

Reads one fuzz run record (schemas/fuzz-run.schema.json) and its triage file
(schemas/fuzz-triage.schema.json) and checks:

  T1  shape:       the triage names the record it triages, every entry has a
                   64-hex input hash, a disposition and a date, covered/new
                   entries name cell, detector and fixture, not-a-bug entries
                   state a reason
  T2  completeness: one entry per finding and one finding per entry; a
                   duplicate entry, an untriaged finding and a stale entry are
                   all errors
  T3  routing:     cell and detector resolve in the registry the triage names,
                   the detector belongs to that cell, and the fixture file
                   exists and holds the cited fixture ID
  T4  agreement:   the record's verdict matches its findings, so a "clean"
                   record cannot carry triage entries and a "findings" record
                   cannot be empty

Exit codes: 0 clean, 1 findings, 2 tool/usage error.

The gate checks that the artifacts exist, not that the routing decision was
right: whether a failure class really needed a new cell is a review judgment.
A record with no findings needs no entries, and that is the only case where an
empty triage file is accepted.

Usage:
    python3 tools/fuzz_triage.py --record spec/fuzz/runs/run.json \
        --triage spec/fuzz/triage/run.yaml [--root .] [--cells registry.yaml]
"""

import argparse
import json
import os
import re
import sys
from datetime import date

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CELL_ID_RE = re.compile(r"^CELL-[0-9]{3,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DISPOSITIONS = ("covered", "new", "not-a-bug")
ENTRY_FIELDS = ("input_sha256", "disposition", "cell", "detector", "fixture",
                "reason", "date", "note")


class Finding(object):
    def __init__(self, check, severity, message, who="-"):
        self.check = check
        self.severity = severity
        self.message = message
        self.who = who

    def render(self):
        return "[%s] %-7s %-14s %s" % (self.check, self.severity, self.who,
                                       self.message)


def load(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML files; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def _valid_date(value):
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _short(digest):
    return digest[:12] if isinstance(digest, str) else "-"


# ---------------------------------------------------------------- T1 shape

def check_shape(record_path, triage, findings):
    if not isinstance(triage, dict):
        findings.append(Finding("T1", "error", "triage is not an object"))
        return []
    for field in ("record", "entries"):
        if field not in triage:
            findings.append(Finding("T1", "error", "missing required field '%s'" % field))
    named = triage.get("record")
    if named is not None:
        if not isinstance(named, str) or not named.strip():
            findings.append(Finding("T1", "error", "record must be a non-empty string"))
        elif os.path.realpath(named) != os.path.realpath(record_path):
            findings.append(Finding("T1", "error",
                                    "triage names record %r but was checked against %r"
                                    % (named, record_path)))

    entries = triage.get("entries")
    if not isinstance(entries, list):
        findings.append(Finding("T1", "error", "entries is not a list"))
        return []

    valid = []
    for i, entry in enumerate(entries):
        who = "#%d" % i
        if not isinstance(entry, dict):
            findings.append(Finding("T1", "error", "entry is not an object", who))
            continue
        valid.append(entry)
        digest = entry.get("input_sha256")
        if isinstance(digest, str):
            who = _short(digest)
        extra = [k for k in entry if k not in ENTRY_FIELDS]
        if extra:
            findings.append(Finding("T1", "error",
                                    "unknown field(s): %s" % ", ".join(sorted(extra)), who))
        for field in ("input_sha256", "disposition", "date"):
            if field not in entry:
                findings.append(Finding("T1", "error", "missing required field '%s'" % field, who))
        if "input_sha256" in entry and not SHA256_RE.match(str(entry["input_sha256"])):
            findings.append(Finding("T1", "error",
                                    "input_sha256 is not a sha256 hex digest", who))
        disposition = entry.get("disposition")
        if disposition is not None and disposition not in DISPOSITIONS:
            findings.append(Finding("T1", "error",
                                    "disposition %r is not one of %s"
                                    % (disposition, ", ".join(DISPOSITIONS)), who))
            continue
        if "date" in entry and not _valid_date(entry.get("date")):
            findings.append(Finding("T1", "error", "date is not YYYY-MM-DD", who))
        if disposition == "not-a-bug":
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                findings.append(Finding("T1", "error",
                                        "disposition not-a-bug requires a non-empty reason", who))
        elif disposition in ("covered", "new"):
            for field in ("cell", "detector", "fixture"):
                value = entry.get(field)
                if not isinstance(value, str) or not value.strip():
                    findings.append(Finding("T1", "error",
                                            "disposition %s requires %s"
                                            % (disposition, field), who))
            cell = entry.get("cell")
            if isinstance(cell, str) and cell and not CELL_ID_RE.match(cell):
                findings.append(Finding("T1", "error",
                                        "cell %r does not match ^CELL-[0-9]{3,}$" % cell, who))
            fixture = entry.get("fixture")
            if isinstance(fixture, str) and fixture and "#" not in fixture:
                findings.append(Finding("T1", "error",
                                        "fixture %r must use the path#MUT-ID form" % fixture, who))
    return valid


# --------------------------------------------------------- T2 completeness

def check_completeness(record, entries, findings):
    recorded = []
    for finding in record.get("findings") or []:
        digest = finding.get("input_sha256") if isinstance(finding, dict) else None
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            findings.append(Finding("T2", "error",
                                    "record has a finding without a sha256 input hash"))
            continue
        recorded.append(digest)

    seen = {}
    for entry in entries:
        digest = entry.get("input_sha256")
        if not isinstance(digest, str):
            continue
        seen[digest] = seen.get(digest, 0) + 1
    for digest, count in sorted(seen.items()):
        if count > 1:
            findings.append(Finding("T2", "error",
                                    "input is triaged %d times" % count, _short(digest)))
    for digest in recorded:
        if digest not in seen:
            findings.append(Finding("T2", "error",
                                    "finding has no triage entry", _short(digest)))
    for digest in seen:
        if digest not in recorded:
            findings.append(Finding("T2", "error",
                                    "triage entry does not match any finding in the record",
                                    _short(digest)))


# -------------------------------------------------------------- T3 routing

def _load_cells(path):
    doc = load(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("cells"), list):
        raise ValueError("registry has no cells list: %s" % path)
    return {cell.get("id"): cell for cell in doc["cells"] if isinstance(cell, dict)}


def _fixture_ids(path):
    doc = load(path)
    ids = doc.get("mutations") if isinstance(doc, dict) else None
    if not isinstance(ids, list):
        return set()
    return {item.get("id") for item in ids if isinstance(item, dict)}


def check_routing(triage, entries, root, cells_path, findings):
    needed = [e for e in entries
              if e.get("disposition") in ("covered", "new") and e.get("cell")]
    if not needed:
        return
    declared = triage.get("cells") or cells_path
    if not declared:
        findings.append(Finding("T3", "error",
                                "triage names cells but no registry: add `cells:` to the "
                                "triage file or pass --cells (V2-18)"))
        return
    cells_abs = declared if os.path.isabs(declared) else os.path.join(root, declared)
    if not os.path.exists(cells_abs):
        findings.append(Finding("T3", "error", "cell registry not found: %s" % declared))
        return
    try:
        cells = _load_cells(cells_abs)
    except (OSError, ValueError) as e:
        findings.append(Finding("T3", "error", "cannot load cell registry: %s" % e))
        return

    for entry in needed:
        who = _short(entry.get("input_sha256"))
        cell_id = entry.get("cell")
        cell = cells.get(cell_id)
        if cell is None:
            findings.append(Finding("T3", "error",
                                    "cell %r is not in %s" % (cell_id, declared), who))
            continue
        detector_ids = [d.get("id") for d in (cell.get("detectors") or [])
                        if isinstance(d, dict)]
        if entry.get("detector") not in detector_ids:
            findings.append(Finding("T3", "error",
                                    "detector %r is not in cell %s"
                                    % (entry.get("detector"), cell_id), who))

        fixture = entry.get("fixture")
        if not isinstance(fixture, str) or "#" not in fixture:
            continue
        rel, fixture_id = fixture.rsplit("#", 1)
        fixture_abs = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.exists(fixture_abs):
            findings.append(Finding("T3", "error",
                                    "fixture file not found: %s" % rel, who))
            continue
        try:
            ids = _fixture_ids(fixture_abs)
        except (OSError, ValueError) as e:
            findings.append(Finding("T3", "error",
                                    "cannot load fixture file %s: %s" % (rel, e), who))
            continue
        if fixture_id not in ids:
            findings.append(Finding("T3", "error",
                                    "fixture %r is not in %s" % (fixture_id, rel), who))


# ------------------------------------------------------------ T4 agreement

def check_agreement(record, findings):
    verdict = record.get("verdict")
    has_findings = bool(record.get("findings"))
    expected = "findings" if has_findings else "clean"
    if verdict not in ("clean", "findings"):
        findings.append(Finding("T4", "error",
                                "record verdict %r is not clean or findings" % verdict))
    elif verdict != expected:
        findings.append(Finding("T4", "error",
                                "record verdict is %r but it holds %d finding(s)"
                                % (verdict, len(record.get("findings") or []))))


def main():
    ap = argparse.ArgumentParser(description="Fuzz finding triage gate (V2-18)")
    ap.add_argument("--record", required=True, help="fuzz run record")
    ap.add_argument("--triage", required=True, help="triage file for that record")
    ap.add_argument("--root", default=None,
                    help="directory that cells and fixture paths are relative to "
                         "(default: current directory)")
    ap.add_argument("--cells", default=None,
                    help="cell registry override; by default the triage file's `cells`")
    args = ap.parse_args()

    root = args.root or os.getcwd()
    for label, path in (("record", args.record), ("triage", args.triage)):
        if not os.path.isfile(path):
            print("%s not found: %s" % (label, path), file=sys.stderr)
            return 2
    try:
        record = load(args.record)
        triage = load(args.triage)
    except (OSError, ValueError) as e:
        print("cannot load input: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(record, dict) or not isinstance(record.get("findings"), list):
        print("record is not a fuzz run record: %s" % args.record, file=sys.stderr)
        return 2

    findings = []
    entries = check_shape(args.record, triage, findings)
    check_completeness(record, entries, findings)
    check_agreement(record, findings)
    check_routing(triage if isinstance(triage, dict) else {}, entries, root,
                  args.cells, findings)

    total = len(record.get("findings") or [])
    print("record: %s | findings: %d | triage entries: %d"
          % (args.record, total, len(entries)))
    for check, label in (("T1", "shape"), ("T2", "completeness"),
                         ("T3", "routing"), ("T4", "agreement")):
        rows = [f for f in findings if f.check == check]
        if not rows:
            print("  %s %-13s OK" % (check, label))
        else:
            print("  %s %-13s %d error(s)" % (check, label, len(rows)))
            for row in rows:
                print("      %s" % row.render())
    errors = sum(1 for f in findings if f.severity == "error")
    print("total: %d error(s)" % errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
