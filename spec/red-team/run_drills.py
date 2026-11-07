#!/usr/bin/env python3
"""Red-team drills against the real pilot artifacts (V2-29 follow-up).

`evals/` proves that a gate rejects a *synthetic* violation the gate author
already knew about. These drills do the opposite: they take the committed
craft-i18n ledger, its committed cargo log and the committed cell registry, apply
one attack each, and run the real gate. A drill passes only when the gate exits
with the expected code AND prints the expected message — a crash or an unrelated
error is not a block.

One drill is recorded as ALLOWED on purpose. It is a gate staying silent, not a
bug in the drill: re-dating a run (the evidence identity includes the date, so
a shifted date is "new evidence"). The harness fails if it stops being allowed,
so the recorded result cannot drift away from the code. Borrowing another
claim's real evidence used to be allowed; L6 now blocks it, and the second
borrowing drill shows that declaring the sharing does not reopen the gap.

The target repository is read, never modified: every attack works on a copy in
a temp directory. The suite needs the craft-i18n checkout and its cargo log at
the recorded commit; without them the drill exits 2 rather than reporting a
result it did not measure.

Usage:
    python3 spec/red-team/run_drills.py [--record PATH] [--only NAME]

Exit codes: 0 every drill matched its recorded expectation, 1 a drill diverged,
2 the stand or an input is unavailable.
"""

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PILOT2_ROOT = os.path.normpath(os.path.join(REPO, "..", "astraoffice",
                                            "craft-i18n"))
LEDGER = os.path.join(REPO, "spec", "pilots", "craft-i18n", "claims.yaml")
REGISTRY = os.path.join(REPO, "spec", "pilots", "craft-i18n", "cells.yaml")
SUITE_GLOB = "crates/craft-i18n-tests/**/*.rs"
PY = sys.executable

# A real commit where tools/claim_lint.py changed, for the planner drill.
PLAN_BASE, PLAN_HEAD = "d311c47~1", "d311c47"


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


def run(argv):
    proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def claim(ledger, cid):
    return next(c for c in ledger["claims"] if c["id"] == cid)


def lint_args(path):
    return [PY, "tools/claim_lint.py", "--root", PILOT2_ROOT,
            "--suite-glob", SUITE_GLOB, "--run-log-root", REPO,
            "--tool-output-root", REPO,
            "--no-vale", path]


def cell_args(path):
    return [PY, "tools/cell_lint.py", "--root", PILOT2_ROOT,
            "--ledger", LEDGER, "--suite-glob", SUITE_GLOB, path]


def status_args(base, target):
    return [PY, "tools/status_diff.py", base, target]


# --------------------------------------------------------------------- drills

def _escalate_proven(td):
    base = load(LEDGER)
    target = copy.deepcopy(base)
    claim(target, "C-01")["status"] = "proven"
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [
        {"gate": "claim_lint", "argv": lint_args(target_path),
         "exit": 1, "contains": ["status=proven requires evidence kind=proof"]},
        {"gate": "status_diff", "argv": status_args(base_path, target_path),
         "exit": 1, "contains": ["C-01: tested -> proven without new evidence"]},
    ]


def _ghost_test(td):
    target = load(LEDGER)
    claim(target, "C-01")["evidence"][0]["tests"].append("test_that_never_ran")
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["test 'test_that_never_ran' is cited but not executed in the run log",
                          "test ID 'test_that_never_ran' not found in suite"]}]


def _artifact_tampered(td):
    target = load(LEDGER)
    claim(target, "C-01")["evidence"][0]["run_record"]["artifact_sha256"] = "0" * 64
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["run_record artifact_sha256 mismatch"]}]


def _log_tampered(td):
    target = load(LEDGER)
    claim(target, "C-01")["evidence"][0]["run_record"]["log_sha256"] = "0" * 64
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["run_record log_sha256 mismatch"]}]


def _counts_inflated(td):
    target = load(LEDGER)
    rr = claim(target, "C-01")["evidence"][0]["run_record"]
    rr["tests_run"] = rr["tests_passed"] = 99
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["disagree with log"]}]


def _removed_claim(td):
    base = load(LEDGER)
    target = copy.deepcopy(base)
    target["claims"] = [c for c in target["claims"] if c["id"] != "C-01"]
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [{"gate": "status_diff", "argv": status_args(base_path, target_path),
             "exit": 1, "contains": ["C-01 removed without a retired entry"]}]


def _tombstone_live_claim(td):
    base = load(LEDGER)
    target = copy.deepcopy(base)
    target["retired"] = [{"id": "C-01",
                          "reason": "Pretend the claim was superseded.",
                          "date": "2026-11-07"}]
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [
        {"gate": "claim_lint", "argv": lint_args(target_path), "exit": 1,
         "contains": ["claim is both active and retired"]},
        {"gate": "status_diff", "argv": status_args(base_path, target_path),
         "exit": 1, "contains": ["C-01 is both active and retired"]},
    ]


def _runtime_cell(registry):
    """The cell that claims runtime enforcement; selected by shape, not by ID."""
    return next(c for c in registry["cells"]
                if any(d.get("kind") == "runtime-enforcement"
                       for d in c.get("detectors") or []))


def _cell_missing_artifact(td):
    registry = load(REGISTRY)
    det = _runtime_cell(registry)["detectors"][0]
    det["artifact"] = "crates/absent.rs"
    path = os.path.join(td, "cells.yaml")
    dump(registry, path)
    return [{"gate": "cell_lint", "argv": cell_args(path), "exit": 1,
             "contains": ["artifact not found: crates/absent.rs"]}]


def _cell_runtime_without_response(td):
    registry = load(REGISTRY)
    _runtime_cell(registry).pop("violation_response", None)
    path = os.path.join(td, "cells.yaml")
    dump(registry, path)
    return [{"gate": "cell_lint", "argv": cell_args(path), "exit": 1,
             "contains": ["violation_response must be a non-empty string (V2-15)"]}]


def _stale_proof(td):
    record = os.path.join(td, "record.json")
    with open(record, "w", encoding="utf-8") as f:
        json.dump({
            "tool": "TLC", "command": "java -jar tla2tools.jar P1.tla",
            "output": "P1.log", "output_sha256": "0" * 64, "exit_code": 0,
            "started_at": "2026-11-01T10:00:00+00:00",
            "finished_at": "2026-11-01T10:05:00+00:00",
            "status": "completed",
        }, f)
    manifest = os.path.join(td, "manifest.yaml")
    with open(manifest, "w", encoding="utf-8") as f:
        yaml.safe_dump({"version": 1, "proofs": [{
            "id": "P-01", "claim": "C-18",
            "artifact": "spec/pilots/rbac_pg/cells.yaml",
            "tool_output": record,
            "depends_on": ["tools/claim_lint.py"],
            "assumptions": ["The drill reuses the file as a stand-in artifact."],
        }]}, f, sort_keys=False)
    return [{"gate": "proof_plan",
             "argv": [PY, "tools/proof_plan.py", "--repo", REPO,
                      "--base", PLAN_BASE, "--head", PLAN_HEAD,
                      "--manifest", manifest, "--require-fresh"],
             "exit": 1, "contains": ["RERUN P-01", "must be re-run"]}]


def _redated_run(td):
    """ALLOWED: shift the run's date, add no new run, escalate reviewed->tested."""
    base = load(LEDGER)
    target = copy.deepcopy(base)
    for ledger, day in ((base, "2026-11-05"), (target, "2026-11-06")):
        c = claim(ledger, "C-01")
        c["status"] = "reviewed" if ledger is base else "tested"
        c["evidence"][0]["date"] = day
        rr = c["evidence"][0]["run_record"]
        for field in ("started_at", "finished_at"):
            stamp = datetime.fromisoformat(rr[field]).replace(
                year=int(day[:4]), month=int(day[5:7]), day=int(day[8:10]))
            rr[field] = stamp.isoformat()
        c["last_verified"] = day
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [
        {"gate": "claim_lint", "argv": lint_args(target_path), "exit": 0,
         "contains": ["L2 evidence      OK"]},
        {"gate": "status_diff", "argv": status_args(base_path, target_path),
         "exit": 0, "contains": ["C-01: reviewed -> tested with 1 new evidence entry"]},
    ]


def _borrowed_evidence(td):
    """BLOCKED by L6: an open claim takes another claim's real tests and becomes tested."""
    base = load(LEDGER)
    target = copy.deepcopy(base)
    c8 = claim(target, "C-08")
    c8["status"] = "tested"
    c8["evidence"] = copy.deepcopy(claim(target, "C-01")["evidence"])
    c8.pop("limitations", None)
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [
        {"gate": "claim_lint", "argv": lint_args(target_path), "exit": 1,
         "contains": ["not declared in shared_tests with a reason (V2-34)",
                      "needs at least one test of its own (V2-34)"]},
        {"gate": "status_diff", "argv": status_args(base_path, target_path),
         "exit": 0, "contains": ["C-08: open -> tested with 1 new evidence entry"]},
    ]


def _sanitizer_finding(td):
    """BLOCKED: a record declares a clean ASan run over output with a finding."""
    target = load(LEDGER)
    ev = next(e for e in claim(target, "C-02")["evidence"]
              if e.get("sanitizer_runs"))
    run = ev["sanitizer_runs"][0]
    text = (
        "============================= test session starts =============================\n"
        "collected 1 item\n\n"
        "tests/locales.rs::bad_row_names_file_and_line ... ok\n\n"
        "=================================================================\n"
        "==4213==ERROR: AddressSanitizer: heap-use-after-free on address 0x602000000010\n"
        "READ of size 4 at 0x602000000010 thread T0\n"
        "    #0 0x55d4c0 in craft_i18n_tests::catalog::parse_row\n"
        "SUMMARY: AddressSanitizer: heap-use-after-free\n"
        "==4213==ABORTING\n"
        "=================================================================\n"
    )
    log = os.path.join(td, "asan-finding.log")
    with open(log, "w", encoding="utf-8") as f:
        f.write(text)
    run["output"] = log
    run["output_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["declares a clean run (status=completed, exit_code=0) "
                          "but its output carries a sanitizer finding line"]}]


def _hidden_static_finding(td):
    """BLOCKED by L2: a real finding the record triaged as a gap disappears."""
    target = load(LEDGER)
    runs = claim(target, "C-09")["evidence"][0]["static_analysis_runs"]
    runs[0]["triage"] = [t for t in runs[0]["triage"]
                         if t["finding"] != "F-005"]
    path = os.path.join(td, "ledger.yaml")
    dump(target, path)
    return [{"gate": "claim_lint", "argv": lint_args(path), "exit": 1,
             "contains": ["finding(s) F-005 have no triage entry"]}]


def _borrowed_evidence_declared(td):
    """BLOCKED by L6 rule 2 even when both claims declare the shared test."""
    base = load(LEDGER)
    target = copy.deepcopy(base)
    c1 = claim(target, "C-01")
    tid = c1["evidence"][0]["tests"][0]
    c1["evidence"][0].setdefault("shared_tests", []).append({
        "id": tid, "reason": "The attack declares that the test is shared."})
    c8 = claim(target, "C-08")
    c8["status"] = "tested"
    ev = copy.deepcopy(c1["evidence"][0])
    ev["tests"] = [tid]
    ev["shared_tests"] = [{
        "id": tid, "reason": "The attack declares that the test is shared."}]
    c8["evidence"] = [ev]
    c8.pop("limitations", None)
    base_path, target_path = os.path.join(td, "base.yaml"), os.path.join(td, "target.yaml")
    dump(base, base_path)
    dump(target, target_path)
    return [
        {"gate": "claim_lint", "argv": lint_args(target_path), "exit": 1,
         "contains": ["C-08", "needs at least one test of its own (V2-34)"]},
        {"gate": "status_diff", "argv": status_args(base_path, target_path),
         "exit": 0, "contains": ["C-08: open -> tested with 1 new evidence entry"]},
    ]


DRILLS = [
    {"name": "escalate-tested-to-proven", "build": _escalate_proven,
     "attack": "raise C-01 tested -> proven with the same run record",
     "verdict": "blocked"},
    {"name": "cite-a-test-that-never-ran", "build": _ghost_test,
     "attack": "add a test ID to C-01 that the committed log does not contain",
     "verdict": "blocked"},
    {"name": "artifact-bytes-tampered", "build": _artifact_tampered,
     "attack": "change C-01's artifact_sha256",
     "verdict": "blocked"},
    {"name": "log-bytes-tampered", "build": _log_tampered,
     "attack": "change C-01's log_sha256",
     "verdict": "blocked"},
    {"name": "counts-inflated", "build": _counts_inflated,
     "attack": "claim 99/99 tests when the log says 26/26",
     "verdict": "blocked"},
    {"name": "remove-claim-without-tombstone", "build": _removed_claim,
     "attack": "drop C-01 from the ledger",
     "verdict": "blocked"},
    {"name": "tombstone-a-live-claim", "build": _tombstone_live_claim,
     "attack": "retire C-01 while it is still active",
     "verdict": "blocked"},
    {"name": "cell-detector-artifact-missing", "build": _cell_missing_artifact,
     "attack": "point the runtime detector at a path that does not exist",
     "verdict": "blocked"},
    {"name": "cell-runtime-without-response", "build": _cell_runtime_without_response,
     "attack": "drop violation_response from the runtime-enforcement cell",
     "verdict": "blocked"},
    {"name": "stale-proof-passes-gate", "build": _stale_proof,
     "attack": "declare a proof whose record predates a change to its dependency",
     "verdict": "blocked"},
    {"name": "redate-the-same-run", "build": _redated_run,
     "attack": "shift the run date by one day and escalate reviewed -> tested",
     "verdict": "allowed",
     "gap": "the evidence identity includes the date, so a shifted date is new evidence"},
    {"name": "borrow-another-claims-evidence", "build": _borrowed_evidence,
     "attack": "give the open C-08 claim C-01's real tests and call it tested",
     "verdict": "blocked"},
    {"name": "borrow-and-declare-sharing", "build": _borrowed_evidence_declared,
     "attack": "borrow one of C-01's tests and declare it shared; C-08 still has no test of its own",
     "verdict": "blocked"},
    {"name": "sanitizer-findings-hidden", "build": _sanitizer_finding,
     "attack": "declare a clean ASan run over output that carries an ERROR: AddressSanitizer line",
     "verdict": "blocked"},
    {"name": "static-findings-hidden", "build": _hidden_static_finding,
     "attack": "drop the triage entry for a real static-analysis finding (F-005)",
     "verdict": "blocked"},
]


def check_stand():
    if not os.path.isdir(PILOT2_ROOT):
        return "craft-i18n checkout not found: %s" % PILOT2_ROOT
    if not os.path.isfile(LEDGER):
        return "ledger not found: %s" % LEDGER
    if not os.path.isfile(REGISTRY):
        return "registry not found: %s" % REGISTRY
    log = os.path.join(REPO, "spec", "pilots", "craft-i18n", "runs",
                       "cargo-test-2026-11-07.log")
    if not os.path.isfile(log):
        return "the committed run log is missing: %s" % log
    return None


def run_drill(drill):
    td = tempfile.mkdtemp(prefix="red-team-%s-" % drill["name"])
    problems = []
    try:
        runs = drill["build"](td)
        for spec in runs:
            code, out = run(spec["argv"])
            if code != spec["exit"]:
                problems.append("%s: expected exit %s, got %d (%s)"
                                % (spec["gate"], spec["exit"], code,
                                   out.strip().splitlines()[-1][:160]
                                   if out.strip() else "no output"))
                continue
            for needle in spec["contains"]:
                if needle not in out:
                    problems.append("%s: output does not contain %r"
                                    % (spec["gate"], needle))
        # An `allowed` drill needs no extra check here: if a future gate starts
        # blocking it, the expected exit code above stops matching and the
        # drill fails, which forces the recorded gap to be updated.
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", default=None,
                    help="write the result table as JSON")
    ap.add_argument("--only", default=None, help="run one drill by name")
    args = ap.parse_args()

    stand = check_stand()
    if stand:
        print("error: %s" % stand, file=sys.stderr)
        return 2

    drills = DRILLS
    if args.only:
        drills = [d for d in DRILLS if d["name"] == args.only]
        if not drills:
            print("error: unknown drill %s" % args.only, file=sys.stderr)
            return 2

    rows, failed = [], 0
    for drill in drills:
        problems = run_drill(drill)
        if problems:
            failed += 1
            print("FAIL %-34s %s" % (drill["name"], drill["verdict"]))
            for problem in problems:
                print("     %s" % problem)
            rows.append({"name": drill["name"], "verdict": drill["verdict"],
                         "attack": drill["attack"], "problems": problems})
        else:
            print("ok   %-34s %-7s %s"
                  % (drill["name"], drill["verdict"], drill["attack"]))
            row = {"name": drill["name"], "verdict": drill["verdict"],
                   "attack": drill["attack"]}
            if drill.get("gap"):
                row["gap"] = drill["gap"]
            rows.append(row)

    blocked = sum(1 for r in rows if r["verdict"] == "blocked")
    allowed = sum(1 for r in rows if r["verdict"] == "allowed")
    print("%d/%d drills matched: %d blocked, %d allowed by a recorded gap"
          % (len(rows) - failed, len(rows), blocked, allowed))

    if args.record:
        stamp = datetime.now().date().isoformat()
        if os.path.basename(args.record)[:10] != stamp:
            print("note: record name does not start with the run date %s" % stamp)
        payload = {
            "format": "dev-sec-skills/red-team/v1",
            "date": stamp,
            "ledger": os.path.relpath(LEDGER, REPO),
            "registry": os.path.relpath(REGISTRY, REPO),
            "drills": rows,
            "summary": {"drills": len(rows), "blocked": blocked,
                        "allowed": allowed, "failed": failed},
        }
        parent = os.path.dirname(os.path.abspath(args.record))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.record, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("record written to %s" % args.record)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
