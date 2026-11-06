#!/usr/bin/env python3
"""Cell registry linter — the executable part of the cell contract.

Implements checks over a cell registry (JSON or YAML, see
spec/conveyor/cell-registry.schema.json):

  CL1  structure:     required fields, stable IDs, unique IDs, status/kind/
                      failure-mode enums, detector fields
  CL2  coverage:      a non-open cell needs a detector; a cell may not claim
                      more than its strongest detector; a detector may not
                      claim more than its kind allows; a detector without a
                      mutation fixture is an error for security and correctness
                      cells and a warning otherwise
  CL3  evidence:      detector artifacts exist, dates are valid, not in the
                      future, and within the freshness window
  CL4  traceability:  claim IDs resolve in the claim ledger, a non-open cell
                      has an owner and residual risk, the cell does not claim
                      more than its linked claims
  CL5  taxonomy:      classes are declared, IDs and titles are unique, unused
                      classes and duplicate failure classes are visible
  CL6  escalation:    with --base, a cell may not rise on the status ladder
                      unless the target adds new detector evidence

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 tool/usage error.

Usage:
    python3 tools/cell_lint.py [--root PATH] [--ledger PATH]
                               [--max-age-days N] [--base PATH] registry.yaml
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

STATUSES = ["open", "reviewed", "static-refinement", "tested", "model-checked", "proven"]
STATUS_RANK = {s: i for i, s in enumerate(STATUSES)}
KINDS = {"test", "rule", "invariant", "proof", "fuzz", "review"}
KIND_MAX_RANK = {
    "review": STATUS_RANK["reviewed"],
    "rule": STATUS_RANK["static-refinement"],
    "test": STATUS_RANK["tested"],
    "fuzz": STATUS_RANK["tested"],
    "invariant": STATUS_RANK["model-checked"],
    "proof": STATUS_RANK["proven"],
}
TAXONOMY_CLASSES = {"security", "correctness", "maintainability", "performance"}
MUTATION_REQUIRED_CLASSES = {"security", "correctness"}
FAILURE_MODES = {"deny", "abort", "rollback", "safe-degrade", "detect"}
CELL_ID_RE = re.compile(r"^CELL-[0-9]{3,}$")
DETECTOR_ID_RE = re.compile(r"^D-[A-Za-z0-9._-]+$")
CLAIM_ID_RE = re.compile(r"^C-[0-9]{2,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Finding:
    def __init__(self, check, severity, message, who="-", file=None):
        self.check = check
        self.severity = severity  # "error" | "warning" | "info"
        self.message = message
        self.who = who
        self.file = file

    def render(self):
        loc = " %s" % self.file if self.file else ""
        return "[%s] %-5s %-8s %s%s" % (self.check, self.severity, self.who,
                                        self.message, loc)


def load_doc(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML registries; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def iso(value):
    """Return YYYY-MM-DD for a string/date/datetime, else the original value."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return value


def parse_date(value):
    value = iso(value)
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


# ------------------------------------------------------------ CL1 structure

def check_structure(doc, findings):
    if not isinstance(doc, dict):
        findings.append(Finding("CL1", "error", "registry is not an object"))
        return []
    cells = doc.get("cells")
    if not isinstance(cells, list) or not cells:
        findings.append(Finding("CL1", "error", "no cells array found"))
        return []

    taxonomy = doc.get("taxonomy")
    if not isinstance(taxonomy, dict):
        findings.append(Finding("CL1", "warning", "no taxonomy object; CL5 classes cannot be checked"))
    elif not taxonomy.get("name") or not taxonomy.get("version"):
        findings.append(Finding("CL1", "warning", "taxonomy needs name and version"))

    seen = set()
    valid = []
    for i, cell in enumerate(cells):
        who = cell.get("id", "#%d" % i) if isinstance(cell, dict) else "#%d" % i
        if not isinstance(cell, dict):
            findings.append(Finding("CL1", "error", "cell is not an object", who))
            continue
        valid.append(cell)

        for field in ("id", "title", "taxonomy_class", "entry_points",
                      "failure_mode", "coverage_status", "owner"):
            if field not in cell:
                findings.append(Finding("CL1", "error", "missing required field '%s'" % field, who))

        cid = cell.get("id", "")
        if not CELL_ID_RE.match(str(cid)):
            findings.append(Finding("CL1", "error",
                                    "ID %r does not match ^CELL-[0-9]{3,}$" % cid, who))
        if cid in seen:
            findings.append(Finding("CL1", "error", "duplicate cell ID", who))
        seen.add(cid)

        title = cell.get("title")
        if not isinstance(title, str) or len(title) < 10:
            findings.append(Finding("CL1", "error", "title must be at least 10 characters", who))

        if cell.get("taxonomy_class") not in TAXONOMY_CLASSES:
            findings.append(Finding("CL1", "error",
                                    "unknown taxonomy_class %r" % cell.get("taxonomy_class"), who))

        eps = cell.get("entry_points")
        if not isinstance(eps, list) or not eps or not all(isinstance(e, str) for e in eps):
            findings.append(Finding("CL1", "error",
                                    "entry_points must be a non-empty list of strings", who))

        if cell.get("failure_mode") not in FAILURE_MODES:
            findings.append(Finding("CL1", "error",
                                    "unknown failure_mode %r" % cell.get("failure_mode"), who))

        status = cell.get("coverage_status")
        if status not in STATUSES:
            findings.append(Finding("CL1", "error", "unknown coverage_status %r" % status, who))
        if status == "open" and not cell.get("limitations"):
            findings.append(Finding("CL1", "error", "status=open requires limitations", who))

        owner = cell.get("owner")
        if not isinstance(owner, str) or not owner.strip():
            findings.append(Finding("CL1", "error", "owner must be a non-empty string", who))

        detectors = cell.get("detectors")
        if detectors is not None and not isinstance(detectors, list):
            findings.append(Finding("CL1", "error", "detectors must be a list", who))
            detectors = []
        det_seen = set()
        for j, det in enumerate(detectors or []):
            if not isinstance(det, dict):
                findings.append(Finding("CL1", "error", "detectors[%d] is not an object" % j, who))
                continue
            for field in ("id", "kind", "status"):
                if field not in det:
                    findings.append(Finding("CL1", "error",
                                            "detectors[%d] missing '%s'" % (j, field), who))
            did = det.get("id", "")
            if not DETECTOR_ID_RE.match(str(did)):
                findings.append(Finding("CL1", "error",
                                        "detector ID %r does not match ^D-[A-Za-z0-9._-]+$" % did, who))
            if did in det_seen:
                findings.append(Finding("CL1", "warning", "duplicate detector ID %r" % did, who))
            det_seen.add(did)
            if det.get("kind") not in KINDS:
                findings.append(Finding("CL1", "error",
                                        "detector %r has unknown kind %r" % (did, det.get("kind")), who))
            if det.get("status") not in STATUSES:
                findings.append(Finding("CL1", "error",
                                        "detector %r has unknown status %r" % (did, det.get("status")), who))
            if det.get("kind") == "test" and not (det.get("artifact") or det.get("command")):
                findings.append(Finding("CL1", "error",
                                        "test detector %r needs artifact or command" % did, who))
            if "mutation_exemption" in det:
                exemption = det.get("mutation_exemption")
                if not isinstance(exemption, str) or not exemption.strip():
                    findings.append(Finding("CL1", "error",
                                            "detector %r mutation_exemption must be a non-empty string"
                                            % did, who))
                if det.get("mutation_fixture"):
                    findings.append(Finding("CL1", "warning",
                                            "detector %r has both mutation_fixture and mutation_exemption"
                                            % did, who))

        for j, claim_id in enumerate(cell.get("claim_ids") or []):
            if not CLAIM_ID_RE.match(str(claim_id)):
                findings.append(Finding("CL1", "error",
                                        "claim_ids[%d] %r does not match ^C-[0-9]{2,}$"
                                        % (j, claim_id), who))
    return valid


# ------------------------------------------------------------- CL2 coverage

def check_coverage(cells, findings):
    for cell in cells:
        who = cell.get("id", "-")
        status = cell.get("coverage_status")
        taxonomy_class = cell.get("taxonomy_class")
        detectors = [d for d in (cell.get("detectors") or []) if isinstance(d, dict)]

        if status in STATUSES and status != "open" and not detectors:
            findings.append(Finding("CL2", "error",
                                    "coverage_status=%s requires at least one detector" % status, who))

        if status in STATUSES and detectors:
            strongest = max((STATUS_RANK.get(d.get("status"), 0) for d in detectors), default=0)
            if STATUS_RANK[status] > strongest:
                findings.append(Finding("CL2", "error",
                                        "cell claims %s but its strongest detector is %s"
                                        % (status, STATUSES[strongest]), who))

        for det in detectors:
            did = det.get("id", "-")
            kind = det.get("kind")
            det_status = det.get("status")
            if kind in KIND_MAX_RANK and det_status in STATUS_RANK:
                if STATUS_RANK[det_status] > KIND_MAX_RANK[kind]:
                    findings.append(Finding("CL2", "error",
                                            "detector %r kind=%s cannot claim %s"
                                            % (did, kind, det_status), who))
            if det_status != "open" and not det.get("mutation_fixture"):
                exemption = det.get("mutation_exemption")
                if isinstance(exemption, str) and exemption.strip():
                    findings.append(Finding("CL2", "info",
                                            "detector %r is exempt from a mutation fixture: %s"
                                            % (did, exemption), who))
                elif taxonomy_class in MUTATION_REQUIRED_CLASSES:
                    findings.append(Finding("CL2", "error",
                                            "detector %r (%s) has no mutation_fixture and no "
                                            "mutation_exemption; add a fixture to mutations.yaml "
                                            "or a documented exemption - %s detectors must be "
                                            "shown to fail"
                                            % (did, taxonomy_class, taxonomy_class), who))
                else:
                    findings.append(Finding("CL2", "warning",
                                            "detector %r has no mutation_fixture; it is not verified" % did,
                                            who))

        if status == "open" and detectors:
            findings.append(Finding("CL2", "warning",
                                    "cell is open but already lists detectors", who))
        if status == "open" and not cell.get("residual_risk"):
            findings.append(Finding("CL2", "warning", "open cell has no residual_risk", who))


# ------------------------------------------------------------- CL3 evidence

def check_evidence(doc, cells, root, max_age_days, findings):
    today = date.today()

    def check_date(value, who, label):
        if value is None:
            return
        d = parse_date(value)
        if d is None:
            findings.append(Finding("CL3", "warning", "%s %r is not YYYY-MM-DD"
                                    % (label, iso(value)), who))
            return
        if d > today:
            findings.append(Finding("CL3", "warning", "%s dated in the future: %s" % (label, d), who))
        elif (today - d).days > max_age_days:
            findings.append(Finding("CL3", "warning",
                                    "stale %s: %s (%d days old, window %d)"
                                    % (label, d, (today - d).days, max_age_days), who))

    generated = doc.get("generated") if isinstance(doc, dict) else None
    check_date(generated, "-", "registry generated")

    for cell in cells:
        who = cell.get("id", "-")
        check_date(cell.get("last_seen"), who, "last_seen")
        for det in (cell.get("detectors") or []):
            if not isinstance(det, dict):
                continue
            did = det.get("id", "-")
            artifact = det.get("artifact")
            if artifact and not re.match(r"^[a-z]+://", str(artifact)):
                if not os.path.exists(os.path.join(root, str(artifact))):
                    findings.append(Finding("CL3", "error",
                                            "detector %r artifact not found: %s" % (did, artifact), who))
            check_date(det.get("last_verified"), "%s/%s" % (who, did), "last_verified")
            if det.get("status") != "open" and not det.get("last_verified"):
                findings.append(Finding("CL3", "warning",
                                        "detector %r is non-open but has no last_verified" % did, who))


# --------------------------------------------------------- CL4 traceability

def check_traceability(cells, ledger_path, findings):
    claim_status = {}
    if ledger_path:
        try:
            ledger = load_doc(ledger_path)
        except (OSError, ValueError) as e:
            findings.append(Finding("CL4", "error", "cannot load claim ledger: %s" % e))
            ledger = None
        if isinstance(ledger, dict):
            for c in ledger.get("claims") or []:
                if isinstance(c, dict) and c.get("id"):
                    claim_status[c["id"]] = c.get("status")
        for cell in cells:
            who = cell.get("id", "-")
            ids = cell.get("claim_ids") or []
            if not ids:
                findings.append(Finding("CL4", "info",
                                        "cell is not linked to a claim", who))
            for cid in ids:
                if cid not in claim_status:
                    findings.append(Finding("CL4", "error",
                                            "claim %r not found in ledger" % cid, who))
                else:
                    c_rank = STATUS_RANK.get(claim_status.get(cid), 0)
                    cell_rank = STATUS_RANK.get(cell.get("coverage_status"), 0)
                    if cell_rank > c_rank:
                        findings.append(Finding("CL4", "warning",
                                                "cell claims %s but linked claim %s is %s"
                                                % (cell.get("coverage_status"), cid,
                                                   claim_status.get(cid)), who))
    for cell in cells:
        who = cell.get("id", "-")
        status = cell.get("coverage_status")
        owner = str(cell.get("owner") or "").strip()
        if status in STATUSES and status != "open" and owner.lower() == "unassigned":
            findings.append(Finding("CL4", "warning",
                                    "non-open cell has owner 'unassigned'", who))
        if status in STATUSES and status != "open" and not cell.get("residual_risk"):
            findings.append(Finding("CL4", "warning",
                                    "non-open cell has no residual_risk", who))


# -------------------------------------------------------------- CL5 taxonomy

def check_taxonomy(doc, cells, findings):
    if not isinstance(doc, dict):
        return
    taxonomy = doc.get("taxonomy")
    classes = []
    if isinstance(taxonomy, dict):
        classes = taxonomy.get("classes") or []
        if not isinstance(classes, list) or not classes:
            findings.append(Finding("CL5", "warning", "taxonomy.classes is empty"))
            classes = []
    used = set()
    titles = {}
    failure_classes = {}
    for cell in cells:
        who = cell.get("id", "-")
        cls = cell.get("taxonomy_class")
        used.add(cls)
        if classes and cls not in classes:
            findings.append(Finding("CL5", "error",
                                    "taxonomy_class %r is not declared in taxonomy.classes" % cls, who))

        title = cell.get("title")
        if title:
            key = str(title).strip().lower()
            if key in titles:
                findings.append(Finding("CL5", "warning",
                                        "duplicate title with %s" % titles[key], who))
            else:
                titles[key] = who

        fc = cell.get("failure_class")
        if fc:
            key = (cls, str(fc).strip().lower())
            if key in failure_classes:
                findings.append(Finding("CL5", "info",
                                        "duplicate failure_class %r also on %s"
                                        % (fc, failure_classes[key]), who))
            else:
                failure_classes[key] = who

        eps = cell.get("entry_points") or []
        if isinstance(eps, list) and len(eps) != len(set(eps)):
            findings.append(Finding("CL5", "warning", "duplicate entry_points", who))

    for cls in classes:
        if cls not in used:
            findings.append(Finding("CL5", "info", "taxonomy class %r is unused" % cls))


# ------------------------------------------------------------ CL6 escalation

def detector_evidence(det):
    """Identity of detector evidence. Status and dates are deliberately out:
    a status edit or a rerun is not new proof."""
    return (
        det.get("kind"),
        det.get("artifact") or "",
        det.get("command") or "",
        det.get("mutation_fixture") or "",
    )


def check_escalation(target_cells, base_path, findings):
    try:
        base_doc = load_doc(base_path)
    except (OSError, ValueError) as e:
        findings.append(Finding("CL6", "error", "cannot load base registry: %s" % e))
        return
    base_cells = {}
    if isinstance(base_doc, dict):
        for c in base_doc.get("cells") or []:
            if isinstance(c, dict) and c.get("id"):
                base_cells[c["id"]] = c
    target_ids = set()
    for cell in target_cells:
        cid = cell.get("id")
        target_ids.add(cid)
        if cid not in base_cells:
            findings.append(Finding("CL6", "info", "cell added since base", cid))
            continue
        base = base_cells[cid]
        t_rank = STATUS_RANK.get(cell.get("coverage_status"), 0)
        b_rank = STATUS_RANK.get(base.get("coverage_status"), 0)
        if t_rank > b_rank:
            base_dets = {d.get("id"): detector_evidence(d)
                         for d in (base.get("detectors") or []) if isinstance(d, dict)}
            new = False
            for det in (cell.get("detectors") or []):
                if not isinstance(det, dict):
                    continue
                if det.get("id") not in base_dets:
                    new = True
                    break
                if detector_evidence(det) != base_dets[det.get("id")]:
                    new = True
                    break
            if not new:
                findings.append(Finding("CL6", "error",
                                        "status rose %s -> %s without new detector evidence"
                                        % (base.get("coverage_status"),
                                           cell.get("coverage_status")), cid))
        elif t_rank < b_rank:
            findings.append(Finding("CL6", "info",
                                    "status downgraded %s -> %s"
                                    % (base.get("coverage_status"),
                                       cell.get("coverage_status")), cid))
    for cid in base_cells:
        if cid not in target_ids:
            findings.append(Finding("CL6", "warning", "cell removed since base", cid))


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Cell registry linter (dev-sec-skills)")
    ap.add_argument("registry", help="path to cell registry (JSON or YAML)")
    ap.add_argument("--root", default=None,
                    help="project root for artifacts (default: registry's directory)")
    ap.add_argument("--ledger", default=None,
                    help="claim ledger used to resolve claim_ids")
    ap.add_argument("--base", default=None,
                    help="base registry for the status-escalation gate")
    ap.add_argument("--require-base", action="store_true",
                    help="fail when --base is absent (use only for the first release)")
    ap.add_argument("--max-age-days", type=int, default=90)
    args = ap.parse_args()

    if args.require_base and not args.base:
        print("base registry required: pass --base, or omit --require-base only for "
              "the first release", file=sys.stderr)
        return 2
    if not os.path.isfile(args.registry):
        print("registry not found: %s" % args.registry, file=sys.stderr)
        return 2
    root = args.root or os.path.dirname(os.path.abspath(args.registry))

    try:
        doc = load_doc(args.registry)
    except (OSError, ValueError) as e:
        print("cannot load registry: %s" % e, file=sys.stderr)
        return 2

    findings = []
    cells = check_structure(doc, findings)
    if cells:
        check_coverage(cells, findings)
        check_evidence(doc, cells, root, args.max_age_days, findings)
        check_traceability(cells, args.ledger, findings)
        check_taxonomy(doc, cells, findings)
        if args.base:
            check_escalation(cells, args.base, findings)

    checks = [("CL1", "structure"), ("CL2", "coverage"), ("CL3", "evidence"),
              ("CL4", "traceability"), ("CL5", "taxonomy")]
    if args.base:
        checks.append(("CL6", "escalation"))

    print("registry: %s | cells: %d" % (args.registry, len(cells)))
    for check, label in checks:
        rows = [f for f in findings if f.check == check]
        if not rows:
            print("  %s %-13s OK" % (check, label))
        else:
            print("  %s %-13s %d error(s), %d warning(s), %d info"
                  % (check, label,
                     sum(1 for f in rows if f.severity == "error"),
                     sum(1 for f in rows if f.severity == "warning"),
                     sum(1 for f in rows if f.severity == "info")))
            for f in rows:
                print("      %s" % f.render())

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")
    print("total: %d error(s), %d warning(s), %d info" % (errors, warnings, infos))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
