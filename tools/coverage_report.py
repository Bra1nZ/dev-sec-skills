#!/usr/bin/env python3
"""Coverage report — what the registry maps, what it does not, what went stale.

Reads one cell registry, optionally its claim ledger and the target suite, and
reports:

  CV1 mapping:     cited symbols (a claim's `tests`, a detector's
                   `negative_test`) resolve in the suite; a cited symbol that
                   does not exist is an error
  CV2 symbols:     suite symbols no artifact, claim or negative test maps:
                   reported with their files; an error only when
                   --max-unmapped is exceeded
  CV3 stale claims: non-open claims whose latest date (last_verified, else the
                   newest evidence date) is missing or older than
                   --max-age-days; an error only when --max-stale-claims is
                   exceeded
  CV4 no fixture:  non-open cells whose test or runtime-enforcement detector has
                   neither mutation_fixture nor mutation_exemption; an error
                   only when --max-cells-without-fixture is exceeded

Symbol extraction is deliberately narrower than claim_lint's test-ID index: an
ID must look like `F3a` / `V15` rather than the first word of a prose label, so
that `report("DELETE FROM ...")` is not counted as a test. Symbol mapping is
file-level: a symbol counts as mapped when its file is a detector artifact, or
the symbol is cited by a claim or a negative test. That is coarse on purpose —
it shows which test files nobody mapped, not whether a detector executes every
test in a mapped file. Counts are (file, symbol) sites, so the same test name in
two files counts twice.

Exit codes: 0 no errors, 1 errors, 2 tool/usage error.

Usage:
    python3 tools/coverage_report.py --cells cells.yaml --root ../target \
        --suite-glob "setup/*.py" [--ledger claims.yaml] [--max-age-days 90] \
        [--max-unmapped N] [--max-stale-claims N] \
        [--max-cells-without-fixture N] [--json report.json]
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from datetime import date, timedelta

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

REPORT_ID_RE = re.compile(r'\breport\(\s*["\']([A-Z]{1,5}\d+[a-z]?)\b')
DEF_TEST_RE = re.compile(r"\bdef\s+(test_[a-zA-Z0-9_]+)")
RUST_TEST_RE = re.compile(
    r"#\[\s*test\s*\]\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FIXTURE_KINDS = ("test", "runtime-enforcement")
SKIP_DIRS = (".git", "target", "node_modules", "__pycache__")


class Finding(object):
    def __init__(self, check, severity, message):
        self.check = check
        self.severity = severity
        self.message = message

    def render(self):
        return "[%s] %-7s %s" % (self.check, self.severity, self.message)


def load(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML files; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def _date(value):
    if isinstance(value, str) and DATE_RE.match(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _rel(path):
    return os.path.normpath(path).replace(os.sep, "/")


def suite_symbols(root, suite_glob):
    """Return {file: set(symbols)} for files matching suite_glob."""
    out = {}
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            path = os.path.join(base, name)
            rel = _rel(os.path.relpath(path, root))
            if not fnmatch.fnmatch(rel, suite_glob):
                continue
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            ids = set(REPORT_ID_RE.findall(text))
            ids.update(DEF_TEST_RE.findall(text))
            ids.update(RUST_TEST_RE.findall(text))
            out[rel] = ids
    return out


def cited_symbols(registry, ledger):
    """Symbols the registry and ledger point at, with their owner for reporting."""
    cited = {}
    for cell in registry.get("cells") or []:
        for detector in cell.get("detectors") or []:
            negative = detector.get("negative_test")
            if isinstance(negative, str) and negative.strip():
                cited.setdefault(negative.strip(), "%s/%s" % (cell.get("id"), detector.get("id")))
    for claim in (ledger or {}).get("claims") or []:
        for evidence in claim.get("evidence") or []:
            for test_id in evidence.get("tests") or []:
                cited.setdefault(str(test_id), claim.get("id"))
    return cited


def detector_artifacts(registry):
    artifacts = set()
    for cell in registry.get("cells") or []:
        for detector in cell.get("detectors") or []:
            artifact = detector.get("artifact")
            if isinstance(artifact, str) and artifact.strip():
                artifacts.add(_rel(artifact))
    return artifacts


def check_mapping(cited, symbols, findings):
    known = set()
    for ids in symbols.values():
        known.update(ids)
    for symbol, owner in sorted(cited.items()):
        if symbol not in known:
            findings.append(Finding("CV1", "error",
                                    "cited symbol %r from %s is not in the suite"
                                    % (symbol, owner)))
    return [symbol for symbol in cited if symbol not in known]


def check_symbols(symbols, artifacts, cited, max_unmapped, findings):
    total = 0
    mapped = 0
    unmapped = {}
    for path, ids in symbols.items():
        for symbol in ids:
            total += 1
            if path in artifacts or symbol in cited:
                mapped += 1
            else:
                unmapped.setdefault(path, set()).add(symbol)
    count = sum(len(ids) for ids in unmapped.values())
    if count:
        sample = "; ".join("%s: %s" % (path, ", ".join(sorted(ids)[:3]))
                           for path, ids in sorted(unmapped.items()))
        findings.append(Finding("CV2", "info",
                                "%d of %d symbols are unmapped (%s)"
                                % (count, total, sample)))
        if max_unmapped is not None and count > max_unmapped:
            findings.append(Finding("CV2", "error",
                                    "unmapped symbols %d exceed --max-unmapped %d"
                                    % (count, max_unmapped)))
    return {"total": total, "mapped": mapped, "unmapped": count,
            "files": {path: sorted(ids) for path, ids in sorted(unmapped.items())}}


def check_stale(ledger, max_age_days, max_stale, findings):
    stale, considered = [], 0
    cutoff = date.today() - timedelta(days=max_age_days)
    for claim in (ledger or {}).get("claims") or []:
        if claim.get("status") == "open":
            continue
        considered += 1
        latest = _date(claim.get("last_verified"))
        if latest is None:
            dates = [_date(ev.get("date")) for ev in claim.get("evidence") or []
                     if isinstance(ev, dict)]
            dates = [d for d in dates if d]
            latest = max(dates) if dates else None
        if latest is None:
            stale.append((claim.get("id"), "no date"))
        elif latest < cutoff:
            stale.append((claim.get("id"), latest.isoformat()))
    if stale:
        findings.append(Finding("CV3", "info",
                                "%d of %d non-open claims are stale: %s"
                                % (len(stale), considered,
                                   ", ".join("%s (%s)" % item for item in stale))))
        if max_stale is not None and len(stale) > max_stale:
            findings.append(Finding("CV3", "error",
                                    "stale claims %d exceed --max-stale-claims %d"
                                    % (len(stale), max_stale)))
    return {"considered": considered, "stale": len(stale),
            "stale_claims": [{"id": cid, "date": value} for cid, value in stale]}


def check_fixtures(registry, max_without, findings):
    without, exempt = [], 0
    for cell in registry.get("cells") or []:
        if cell.get("coverage_status") == "open":
            continue
        for detector in cell.get("detectors") or []:
            if detector.get("kind") not in FIXTURE_KINDS:
                continue
            if detector.get("mutation_exemption"):
                exempt += 1
            elif not detector.get("mutation_fixture"):
                without.append("%s/%s" % (cell.get("id"), detector.get("id")))
    if without:
        findings.append(Finding("CV4", "info",
                                "%d detector(s) have no mutation fixture: %s"
                                % (len(without), ", ".join(without))))
        if max_without is not None and len(without) > max_without:
            findings.append(Finding("CV4", "error",
                                    "detectors without a fixture %d exceed "
                                    "--max-cells-without-fixture %d"
                                    % (len(without), max_without)))
    return {"without_fixture": len(without), "exemptions": exempt,
            "detectors": without}


def main():
    ap = argparse.ArgumentParser(description="Registry coverage report (V2-20)")
    ap.add_argument("--cells", required=True, help="cell registry")
    ap.add_argument("--root", required=True, help="target repository root")
    ap.add_argument("--suite-glob", default=None,
                    help="glob for suite files; without it the symbol checks are skipped")
    ap.add_argument("--ledger", default=None, help="claim ledger (optional)")
    ap.add_argument("--max-age-days", type=int, default=90,
                    help="claim freshness window in days (default 90)")
    ap.add_argument("--max-unmapped", type=int, default=None,
                    help="fail when more suite symbols are unmapped than this")
    ap.add_argument("--max-stale-claims", type=int, default=None,
                    help="fail when more non-open claims are stale than this")
    ap.add_argument("--max-cells-without-fixture", type=int, default=None,
                    help="fail when more detectors lack a fixture than this")
    ap.add_argument("--json", default=None, help="write the summary as JSON")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print("root not found: %s" % args.root, file=sys.stderr)
        return 2
    try:
        registry = load(args.cells)
        ledger = load(args.ledger) if args.ledger else None
    except (OSError, ValueError) as e:
        print("cannot load input: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(registry, dict) or not isinstance(registry.get("cells"), list):
        print("not a cell registry: %s" % args.cells, file=sys.stderr)
        return 2
    if args.ledger and (not isinstance(ledger, dict)
                        or not isinstance(ledger.get("claims"), list)):
        print("not a claim ledger: %s" % args.ledger, file=sys.stderr)
        return 2

    findings = []
    cells = registry["cells"]
    non_open = sum(1 for c in cells if c.get("coverage_status") != "open")
    cited = cited_symbols(registry, ledger)
    artifacts = detector_artifacts(registry)

    summary = {
        "cells": {"total": len(cells), "non_open": non_open,
                  "open": len(cells) - non_open},
        "cited_symbols": len(cited),
    }
    if args.suite_glob:
        symbols = suite_symbols(args.root, args.suite_glob)
        check_mapping(cited, symbols, findings)
        summary["symbols"] = check_symbols(symbols, artifacts, cited,
                                           args.max_unmapped, findings)
    else:
        findings.append(Finding("CV1", "info",
                                "no --suite-glob: cited symbols were not resolved"))
        findings.append(Finding("CV2", "info",
                                "no --suite-glob: symbol coverage was not measured"))
    summary["stale"] = check_stale(ledger, args.max_age_days,
                                   args.max_stale_claims, findings)
    summary["fixtures"] = check_fixtures(registry, args.max_cells_without_fixture,
                                         findings)

    print("coverage: %s | root: %s" % (args.cells, args.root))
    print("  cells: %d (%d non-open, %d open)" % (len(cells), non_open,
                                                  len(cells) - non_open))
    if args.suite_glob:
        symbols = summary["symbols"]
        print("  symbols: %d (mapped %d, unmapped %d)"
              % (symbols["total"], symbols["mapped"], symbols["unmapped"]))
    print("  stale claims: %d of %d (max age %d days)"
          % (summary["stale"]["stale"], summary["stale"]["considered"],
             args.max_age_days))
    print("  detectors without fixture: %d (exemptions %d)"
          % (summary["fixtures"]["without_fixture"],
             summary["fixtures"]["exemptions"]))
    for check, label in (("CV1", "mapping"), ("CV2", "symbols"),
                         ("CV3", "stale claims"), ("CV4", "fixtures")):
        rows = [f for f in findings if f.check == check]
        if not rows:
            print("  %s %-12s OK" % (check, label))
        else:
            for row in rows:
                print("      %s" % row.render())
    errors = sum(1 for f in findings if f.severity == "error")
    print("total: %d error(s)" % errors)

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        os.makedirs(parent, exist_ok=True)
        payload = {"cells": args.cells, "root": args.root,
                   "suite_glob": args.suite_glob, "measured": date.today().isoformat(),
                   "max_age_days": args.max_age_days,
                   "summary": summary,
                   "findings": [{"check": f.check, "severity": f.severity,
                                 "message": f.message} for f in findings]}
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
