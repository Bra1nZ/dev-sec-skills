#!/usr/bin/env python3
"""Claim ledger linter — the executable subset of the evidence-first contract.

Implements phase-1 checks over a claim ledger (JSON or YAML, see
schemas/claim-ledger.schema.json):

  L1  schema:        required fields, stable IDs, unique IDs, status and
                     evidence-kind enums, kind=test requires tests,
                     status=open requires limitations, run_record shape,
                     tool_output shape, sanitizer_runs shape,
                     static_analysis_runs shape, retired tombstones (reason
                     present, never also active)
  L2  evidence:      artifact paths exist, commits resolvable, the artifact
                     matches its blob at the cited commit, dates within the
                     freshness window, run_record log and artifact hashes
                     match, the run exited 0 for a non-open claim, every cited
                     test appears in the captured log with a status,
                     tool_output.output matches its hash and finished_at date,
                     tool_output.status=completed is required for a non-open
                     claim (V2-28), sanitizer_runs outputs match their hashes
                     and a completed exit-0 run must not cite output that
                     carries a sanitizer finding line, static_analysis_runs
                     hash the rule set and both outputs, the report hashes the
                     cited SARIF, the engine is present, unmapped and authored
                     inputs are zero for a non-open claim, and the triage is a
                     bijection with the report's findings that resolves its
                     cells
  L3  traceability:  every test ID in kind=test evidence exists in the suite
  L4  consistency:   status matches the strongest evidence channel; stronger
                     evidence than the status is a warning; model-checked and
                     proven need a tool_output, model-checked needs a bound
  L5  prose:         unqualified absolutes in .md documents. Engine order:
                     Vale (if installed; styles/RussianAbsolutes package),
                     fallback to the built-in line scanner.
  L6  relevance:     a test cited by two claims must be declared in
                     shared_tests with a reason next to each citation, and a
                     non-open claim must cite at least one test no other claim
                     cites (V2-34) — declaring the sharing does not let a claim
                     inherit a neighbour's evidence.

A run_record (schemas/run-record.schema.json) is optional: a kind=test record
without one gets an L2 warning, because re-dating and citing a test that never
ran stay invisible. With one, L2 hashes the log and the artifact and checks
that the cited test IDs appear in the log. This detects re-dating and edited
logs only if the forger does not also rewrite the record; without an external
anchor (C-13) a consistent forgery passes.

A tool_output (schemas/tool-output.schema.json) is required for a claim whose
status is model-checked or proven: an artifact says a model exists, the record
says a tool ran over it and what it answered. L1 checks the shape, L2 hashes
the captured output and ties finished_at to the evidence date. L2 also requires
`status: completed` for a non-open claim, so a timed-out or failed run stays
`unverified` instead of passing with a truncated log (V2-28). It does not
check the tool's semantics or the soundness of the encoding; without an
external anchor a consistent forgery passes, as with run records.

A sanitizer run (schemas/sanitizer-run.schema.json) is dynamic test evidence,
so it is only valid on `kind: test`. A sanitizer can disprove a memory or
undefined-behaviour claim, never prove its absence, so the useful question is
whether the declared outcome agrees with the bytes the run printed. L1 checks
the shape (tool, build_flags, command, output, hash, exit code, timestamps,
status); L2 hashes the output, ties finished_at to the evidence date, requires
`status: completed` for a non-open claim, and rejects a record that declares
`completed` with exit 0 while its own output carries a finding line
(`ERROR: AddressSanitizer:` and the equivalents other sanitizers print, plus
`SUMMARY: ...Sanitizer:`). A bare mention of a sanitizer name in a test's
expected string is not a finding. Recoverable UBSan diagnostics
(`file:line: runtime error:`) are deliberately not matched, because they can
accompany exit code 0. The record does not prove the build was instrumented,
that the corpus exercised the claim, or that the sanitizer would have caught a
different defect.

A static-analysis run (schemas/static-analysis-run.schema.json) is only valid
on `kind: static-analysis` and is the only evidence that can support
`static-refinement`. A finding is a review-queue entry, not a verdict, so the
record carries the engine, the rule set and its hash, the target commit, the
raw SARIF output, the normalized sarif_evidence report and exactly one triage
entry per finding. L1 checks the shape and the disposition vocabulary
(`covered`/`new` name cell, detector and fixture; `not-a-bug`/`out-of-scope`
require a reason). L2 hashes the rules and both outputs, ties finished_at to
the evidence date, requires `completed` with exit 0 for a non-open claim,
checks that the report hashes the cited SARIF, that the named engine is
present, that `unmapped` and `fixture_inputs` are zero, that the triage is a
bijection with the report's findings, and that every `covered`/`new` entry
resolves its cell, detector and fixture in the named registry. A URL for the
SARIF or the report is rejected for a non-open claim, because remote bytes
cannot be hashed locally and the triage cannot be checked against them. An
`out-of-scope` entry records a real finding the cited taxonomy does not own; it
is not a claim that the finding is false.

Commits are anchored too, not just resolved: when the root is a git work tree,
the artifact must exist at the cited commit (the run record's commit when the
evidence item has none) and its bytes must equal the working tree's. A commit
that resolves but is unrelated to the artifact — it predates the file or the
file was edited after it — is an error. Synthetic fixtures without .git skip
the check, so they cannot demonstrate it; the git-backed eval case does.

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 tool/usage error.

Usage:
    python3 tools/claim_lint.py [--root PATH] [--suite-glob GLOB]
                                [--max-age-days N] [--docs-glob GLOB]
                                [--run-log-root PATH] [--tool-output-root PATH]
                                [--no-vale]
                                ledger.json|yaml
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
import anchor_subject  # noqa: E402

STATUSES = {"proven", "model-checked", "tested", "static-refinement", "reviewed", "open"}
EVIDENCE_KINDS = {"proof", "model-check", "test", "static-analysis", "review", "planned"}
STATUS_REQUIRES_KIND = {
    "proven": "proof",
    "model-checked": "model-check",
    "tested": "test",
    "static-refinement": "static-analysis",
    "reviewed": "review",
}
ID_RE = re.compile(r"^C-[0-9]{2,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# report("F8a ...") — the script-suite convention; def test_foo — pytest.
REPORT_ID_RE = re.compile(r'\breport\(\s*["\']([A-Za-z][A-Za-z0-9_-]*)')
DEF_TEST_RE = re.compile(r"\bdef\s+(test_[a-zA-Z0-9_]+)")
# Rust: a stack of attributes containing a test attribute (usually #[test],
# also #[tokio::test] and friends) directly before `fn name`. Doc comments and
# whitespace may sit between the attributes and the fn. Other attributes alone
# do not make a test: #[allow(...)] fn helper is not evidence.
RUST_TEST_RE = re.compile(
    r"(?:#\[[^\]\n]*\]\s*)*#\[(?:[A-Za-z_][A-Za-z0-9_]*::)*test(?:\([^)]*\))?\]"
    r"\s*(?:#\[[^\]\n]*\]\s*)*(?://[^\n]*\n\s*)*fn\s+([A-Za-z_][A-Za-z0-9_]*)")

# Run record (V2-01/V2-02, schemas/run-record.schema.json).
RUN_RECORD_FIELDS = ("runner", "command", "commit", "exit_code", "started_at",
                     "finished_at", "log", "log_sha256", "tests_run", "tests_passed")
# Tool output (V2-10, schemas/tool-output.schema.json): the model checker's or
# prover's own run. Required fields mirror the schema's `required` list.
TOOL_OUTPUT_FIELDS = ("tool", "command", "output", "output_sha256",
                      "exit_code", "finished_at", "status")
TOOL_STATUSES = ("model-checked", "proven")
TOOL_RUN_STATUSES = ("completed", "unverified", "failed", "error")
# Sanitizer run (V2-35, schemas/sanitizer-run.schema.json). A sanitizer run is
# dynamic test evidence, so it hangs off kind=test and carries the run's own
# output instead of a tests list.
SANITIZER_TOOLS = ("asan", "ubsan", "tsan", "msan", "lsan")
SANITIZER_FIELDS = ("tool", "build_flags", "command", "output", "output_sha256",
                    "exit_code", "started_at", "finished_at", "status")
# Finding lines the major sanitizers print when they halt: ASan/LSan/TSan/MSan
# and a non-recovering UBSan prefix the process id and say ERROR or WARNING.
# A recoverable UBSan diagnostic ("file:line: runtime error:") is deliberately
# not matched: with halt_on_error=0 it can accompany exit code 0, so a clean
# record and such a line are not necessarily a contradiction.
SANITIZER_FINDING_RE = re.compile(
    r"^(?:==\d+==)?(?:ERROR|WARNING): "
    r"(?:Address|Leak|UndefinedBehavior|Thread|Memory)Sanitizer:"
    r"|^SUMMARY: (?:Address|Leak|UndefinedBehavior|Thread|Memory)Sanitizer:",
    re.MULTILINE)
# Static-analysis run (V2-36, schemas/static-analysis-run.schema.json). The
# engine's SARIF output is the raw evidence; the normalized sarif_evidence
# report carries the finding identities the triage names. A finding is a
# review-queue entry, so a record needs exactly one disposition per finding
# before it can support a claim.
STATIC_ANALYSIS_FIELDS = ("tool", "command", "rules", "target_commit", "output",
                          "output_sha256", "report", "report_sha256", "exit_code",
                          "started_at", "finished_at", "status", "triage", "anchor")
STATIC_REPORT_FORMAT = "dev-sec-skills/sarif-evidence/v1"
TRIAGE_DISPOSITIONS = ("covered", "new", "not-a-bug", "out-of-scope")
TRIAGE_ROUTED = ("covered", "new")
# Anchor (C-13, schemas/static-analysis-run.schema.json). An SSH signature over
# the canonical bytes of tools/anchor_subject.py binds the run identity, both
# output hashes and the whole triage list. The public key is committed as
# allowed_signers; the private key is not. L2 recomputes the bytes and verifies
# the signature, so a record edited after signing no longer verifies.
ANCHOR_FIELDS = ("type", "signer", "namespace", "subject", "subject_sha256",
                 "signature", "signature_sha256", "allowed_signers", "date")
ANCHOR_TYPES = ("ssh-ed25519",)
FINDING_ID_RE = re.compile(r"^F-[0-9]{3,}$")
CELL_ID_RE = re.compile(r"^CELL-[0-9]{3,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
URL_RE = re.compile(r"^[a-z]+://")
# Summary lines the run-record cross-check understands. cargo prints one per
# test binary, so the counts are summed; pytest prints one per run.
CARGO_SUMMARY_RE = re.compile(
    r"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed;", re.MULTILINE)
PYTEST_SUMMARY_LINE_RE = re.compile(r"^=+ .*\bin [0-9.]+s.*=+$")

# Built-in fallback for L5 (used when Vale is unavailable). English entries
# mirror references/banned-words.md; Russian entries are calibrated on the
# rbac_pg pilot corpus.
BANNED = [
    r"fully tested", r"completely tested", r"guarantees?\b", r"guaranteed\b",
    r"certified\b", r"\bcompliant\b", r"proven secure", r"completely secure",
    r"secure and tested", r"all tests pass",
    r"полностью протестирован\w*", r"гарантирует\w*", r"сертифицирован\w*",
    r"полностью безопасн\w*", r"абсолютно надёжн\w*",
]
# A line carrying any of these is treated as evidence-bearing: the absolute is
# qualified in place, so the fallback scanner downgrades it to info.
EVIDENCE_HINT_RE = re.compile(
    r"\b(?:F|M|C|T|I)-?\d{1,3}[a-z]?\b|docs/|setup/|sql/|\d{4}-\d{2}-\d{2}|[0-9a-f]{7,40}"
)

# Self-claim context rule (L5 post-filter): an absolute is a real finding when
# the nearest context marker to the match is this project's own mechanism
# ("модуль гарантирует"); when the nearest marker names a third-party system
# ("гарантирует платформа", "сертифицированная ОС"), it is downgraded to info.
# Proximity, not line membership: several pilot lines carry both markers
# (FSTEC-GAP.md:258 has "в модуле" and "СКЗИ" on one line), and the absolute
# refers to whichever marker is closer. Calibrated on the rbac_pg corpus:
# 11 of 12 Vale findings are third-party context, only FSTEC-GAP.md:226
# ("Модуль гарантирует: ...") is a true self-claim.
# "rbac" is deliberately absent: "rbac_admin" appears in third-party lines.
SELF_CONTEXT_RE = re.compile(
    r"модул[а-яё]*|расширени[а-яё]*|цитадел[а-яё]*|проект|наш[а-яё]*",
    re.IGNORECASE)
THIRD_PARTY_RE = re.compile(
    r"платформ[а-яё]*|ЗСУБД|Персе[а-яё]*|Astra|AltLinux|pgcrypto|СКЗИ|ФСБ|ГОСТ|\bОС\b",
    re.IGNORECASE)

VALE_CONFIG_TEMPLATE = """StylesPath = {styles}
MinAlertLevel = suggestion
Vocab = RussianAbsolutes

[{root}/**]
BasedOnStyles = RussianAbsolutes
"""


class Finding:
    def __init__(self, check, severity, message, claim=None, file=None, line=None):
        self.check = check
        self.severity = severity  # "error" | "warning" | "info"
        self.message = message
        self.claim = claim
        self.file = file
        self.line = line

    def render(self):
        loc = ""
        if self.file:
            loc = self.file + (":%d" % self.line if self.line else "")
        who = self.claim or "-"
        return "[%s] %-5s %-6s %s %s" % (self.check, self.severity, who, self.message, loc)


def load_ledger(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML ledgers; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def walk_files(root, pattern, skip_dirs=(".git", "node_modules", "__pycache__")):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in names:
            path = os.path.join(base, name)
            # Match the root-relative path so globs like "setup/*.py" work;
            # fnmatch's * crosses directory separators, so "*.py" still
            # matches everything.
            if fnmatch.fnmatch(os.path.relpath(path, root), pattern):
                yield path


def find_vale():
    """Locate the vale binary: VALE env override, PATH, then ~/.local/bin."""
    candidate = os.environ.get("VALE")
    if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    found = shutil.which("vale")
    if found:
        return found
    home = os.path.expanduser("~/.local/bin/vale")
    if os.path.isfile(home) and os.access(home, os.X_OK):
        return home
    return None


# ---------------------------------------------------------------- L1 schema

def _check_shared_tests(ev, j, who, findings):
    """Shape of evidence[].shared_tests (V2-34).

    A test that two claims cite must be declared shared next to each citation,
    with a reason. L1 checks the shape; L6 enforces that the declaration
    exists and that a non-open claim keeps evidence of its own.
    """
    shared = ev.get("shared_tests")
    if shared is None:
        return
    if ev.get("kind") != "test":
        findings.append(Finding("L1", "error",
                                "evidence[%d].shared_tests is only valid for kind=test" % j, who))
        return
    if not isinstance(shared, list):
        findings.append(Finding("L1", "error",
                                "evidence[%d].shared_tests is not a list" % j, who))
        return
    tests = ev.get("tests") or []
    seen = set()
    for k, entry in enumerate(shared):
        if not isinstance(entry, dict):
            findings.append(Finding("L1", "error",
                                    "evidence[%d].shared_tests[%d] is not an object" % (j, k), who))
            continue
        tid = entry.get("id")
        if not isinstance(tid, str) or not tid.strip():
            findings.append(Finding("L1", "error",
                                    "evidence[%d].shared_tests[%d] requires a non-empty id"
                                    % (j, k), who))
        elif tid not in tests:
            findings.append(Finding("L1", "error",
                                    "evidence[%d].shared_tests id %r is not in this evidence "
                                    "item's tests" % (j, tid), who))
        elif tid in seen:
            findings.append(Finding("L1", "error",
                                    "evidence[%d].shared_tests duplicates id %r" % (j, tid), who))
        else:
            seen.add(tid)
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            findings.append(Finding("L1", "error",
                                    "evidence[%d].shared_tests[%d] requires a non-empty reason"
                                    % (j, k), who))


def check_schema(ledger, findings):
    claims = ledger.get("claims") if isinstance(ledger, dict) else None
    if not isinstance(claims, list) or not claims:
        findings.append(Finding("L1", "error", "no claims array found"))
        return []
    seen = set()
    for i, c in enumerate(claims):
        who = c.get("id", "#%d" % i) if isinstance(c, dict) else "#%d" % i
        if not isinstance(c, dict):
            findings.append(Finding("L1", "error", "claim is not an object"))
            continue
        for field in ("id", "claim", "mechanism", "evidence", "scope", "status"):
            if field not in c:
                findings.append(Finding("L1", "error", "missing required field '%s'" % field, who))
        cid = c.get("id", "")
        if not ID_RE.match(str(cid)):
            findings.append(Finding("L1", "error", "ID %r does not match ^C-[0-9]{2,}$" % cid, who))
        if cid in seen:
            findings.append(Finding("L1", "error", "duplicate claim ID", who))
        seen.add(cid)
        if c.get("status") not in STATUSES:
            findings.append(Finding("L1", "error", "unknown status %r" % c.get("status"), who))
        if c.get("status") == "open" and not c.get("limitations"):
            findings.append(Finding("L1", "error", "status=open requires limitations", who))
        for j, ev in enumerate(c.get("evidence") or []):
            if not isinstance(ev, dict) or ev.get("kind") not in EVIDENCE_KINDS:
                findings.append(Finding("L1", "error", "evidence[%d] has unknown kind" % j, who))
                continue
            if ev["kind"] == "test" and not ev.get("tests"):
                findings.append(Finding("L1", "error", "kind=test requires a non-empty tests list", who))
            if ev["kind"] == "test" and not (ev.get("command") or ev.get("artifact")):
                findings.append(Finding("L1", "error", "kind=test requires command or artifact", who))
            _check_shared_tests(ev, j, who, findings)
    return [c for c in claims if isinstance(c, dict)]


# ------------------------------------------------ run records (V2-01/V2-02)

def check_retired(ledger, claims, findings):
    """Validate the tombstone list (V2-05).

    A claim may leave the ledger only through `retired:`, which carries a
    reason. The shape checks live in L1 because they need no base ledger; the
    removal check (a base claim gone without a tombstone) lives in
    tools/status_diff.py, which has the base.
    """
    if not isinstance(ledger, dict):
        return
    retired = ledger.get("retired")
    if retired is None:
        return
    if not isinstance(retired, list):
        findings.append(Finding("L1", "error", "retired is not a list"))
        return
    active = {c.get("id") for c in claims if isinstance(c, dict)}
    seen = set()
    for i, entry in enumerate(retired):
        if not isinstance(entry, dict):
            findings.append(Finding("L1", "error", "retired[%d] is not an object" % i))
            continue
        rid = entry.get("id")
        who = rid if isinstance(rid, str) and rid else "#retired[%d]" % i
        if not isinstance(rid, str) or not ID_RE.match(rid):
            findings.append(Finding("L1", "error",
                                    "retired ID %r does not match ^C-[0-9]{2,}$" % rid, who))
        if rid in seen:
            findings.append(Finding("L1", "error", "duplicate retired ID", who))
        seen.add(rid)
        if rid in active:
            findings.append(Finding("L1", "error",
                                    "claim is both active and retired; retire it once", who))
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            findings.append(Finding("L1", "error", "retired entry requires a non-empty reason", who))
        when = entry.get("date")
        if when is not None and not DATE_RE.match(str(when)):
            findings.append(Finding("L1", "error",
                                    "retired date %r is not YYYY-MM-DD" % when, who))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _log_summary(text):
    """(passed, failed) from a cargo or pytest summary, or None."""
    cargo = CARGO_SUMMARY_RE.findall(text)
    if cargo:
        return (sum(int(p) for p, _ in cargo), sum(int(f) for _, f in cargo))
    for line in reversed(text.splitlines()):
        if PYTEST_SUMMARY_LINE_RE.match(line):
            passed = re.search(r"(\d+) passed", line)
            failed = re.search(r"(\d+) failed", line)
            if passed:
                return (int(passed.group(1)), int(failed.group(1)) if failed else 0)
    return None


def _test_ran(name, text):
    """A cited test ID must sit on a line that carries a run status.

    The runner must name each test: cargo does this by default; pytest needs
    -v or -rA. A log that never names a test cannot support the citation.
    """
    for line in text.splitlines():
        if name in line:
            low = line.lower()
            if ("... ok" in low or "... failed" in low or "... ignored" in low
                    or "passed" in low or "failed" in low):
                return True
    return False


def check_run_records_schema(claims, findings):
    for c in claims:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("kind") != "test":
                continue
            rr = ev.get("run_record")
            if rr is None:
                continue
            if not isinstance(rr, dict):
                findings.append(Finding("L1", "error", "run_record is not an object", c["id"]))
                continue
            missing = [f for f in RUN_RECORD_FIELDS if f not in rr]
            if missing:
                findings.append(Finding("L1", "error",
                                        "run_record missing %s" % ", ".join(missing), c["id"]))
            ev_commit, rr_commit = ev.get("commit"), rr.get("commit")
            if ev_commit and rr_commit and str(ev_commit) != str(rr_commit):
                findings.append(Finding("L1", "error",
                                        "run_record commit %s does not match evidence commit %s"
                                        % (rr_commit, ev_commit), c["id"]))
            if ev.get("command") and rr.get("command") and ev["command"] != rr["command"]:
                findings.append(Finding("L1", "error",
                                        "run_record command does not match evidence command", c["id"]))
            for field in ("log_sha256", "artifact_sha256"):
                value = rr.get(field)
                if value is not None and not SHA256_RE.match(str(value)):
                    findings.append(Finding("L1", "error",
                                            "run_record %s is not a sha256 hex digest" % field, c["id"]))
            artifact = ev.get("artifact")
            if artifact and not URL_RE.match(artifact) and not rr.get("artifact_sha256"):
                findings.append(Finding("L1", "error",
                                        "run_record needs artifact_sha256 for local artifact %s"
                                        % artifact, c["id"]))
            tr, tp = rr.get("tests_run"), rr.get("tests_passed")
            if not isinstance(tr, int) or not isinstance(tp, int):
                findings.append(Finding("L1", "error",
                                        "run_record tests_run/tests_passed must be integers", c["id"]))
            else:
                if tr < 1 or tp < 1:
                    findings.append(Finding("L1", "error",
                                            "run_record tests_run/tests_passed must be >= 1", c["id"]))
                if tp > tr:
                    findings.append(Finding("L1", "error",
                                            "run_record tests_passed (%d) exceeds tests_run (%d)"
                                            % (tp, tr), c["id"]))
                cited = len(set(ev.get("tests") or []))
                if cited > tr:
                    findings.append(Finding("L1", "error",
                                            "more cited test IDs (%d) than executed tests (%d)"
                                            % (cited, tr), c["id"]))
            if not isinstance(rr.get("exit_code"), int):
                findings.append(Finding("L1", "error",
                                        "run_record exit_code must be an integer", c["id"]))
            for field in ("started_at", "finished_at"):
                value = rr.get(field)
                if value is not None and _parse_iso(value) is None:
                    findings.append(Finding("L1", "error",
                                            "run_record %s is not an ISO 8601 timestamp" % field, c["id"]))


def check_tool_outputs_schema(claims, findings):
    """L1 shape for evidence.tool_output (V2-10).

    An artifact says a model exists; this record says a tool ran over it and
    what it answered. The shape has to hold before the run can be trusted, so
    every field the schema requires is checked here, before L2 looks at the
    files.
    """
    for c in claims:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("tool_output") is None:
                continue
            to = ev.get("tool_output")
            cid = c["id"]
            if not isinstance(to, dict):
                findings.append(Finding("L1", "error", "tool_output is not an object", cid))
                continue
            missing = [f for f in TOOL_OUTPUT_FIELDS if f not in to]
            if missing:
                findings.append(Finding("L1", "error",
                                        "tool_output missing %s" % ", ".join(missing), cid))
            for field in ("tool", "command", "output"):
                value = to.get(field)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    findings.append(Finding("L1", "error",
                                            "tool_output %s must be a non-empty string" % field, cid))
            if to.get("output_sha256") is not None and not SHA256_RE.match(str(to.get("output_sha256"))):
                findings.append(Finding("L1", "error",
                                        "tool_output output_sha256 is not a sha256 hex digest", cid))
            if not isinstance(to.get("exit_code"), int):
                findings.append(Finding("L1", "error",
                                        "tool_output exit_code must be an integer", cid))
            for field in ("started_at", "finished_at"):
                value = to.get(field)
                if value is not None and _parse_iso(value) is None:
                    findings.append(Finding("L1", "error",
                                            "tool_output %s is not an ISO 8601 timestamp" % field, cid))
            for field in ("version", "verdict", "bound"):
                value = to.get(field)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    findings.append(Finding("L1", "error",
                                            "tool_output %s must be a non-empty string" % field, cid))
            # V2-28: a bounded run must say how it ended. Without an explicit
            # status a killed run and a completed run look the same once the
            # log is truncated.
            run_status = to.get("status")
            if run_status is not None and run_status not in TOOL_RUN_STATUSES:
                findings.append(Finding("L1", "error",
                                        "tool_output status=%r is not one of %s (V2-28)"
                                        % (run_status, ", ".join(TOOL_RUN_STATUSES)), cid))
            timed_out = to.get("timed_out")
            if timed_out is not None and not isinstance(timed_out, bool):
                findings.append(Finding("L1", "error",
                                        "tool_output timed_out must be a boolean", cid))
            if timed_out is True and run_status not in (None, "unverified"):
                findings.append(Finding("L1", "error",
                                        "tool_output timed_out=true contradicts status=%r (V2-28)"
                                        % run_status, cid))
            bound_seconds = to.get("bound_seconds")
            if bound_seconds is not None and (not isinstance(bound_seconds, int)
                                             or isinstance(bound_seconds, bool)
                                             or bound_seconds < 1):
                findings.append(Finding("L1", "error",
                                        "tool_output bound_seconds must be an integer >= 1", cid))
            elapsed = to.get("elapsed_seconds")
            if elapsed is not None and (not isinstance(elapsed, (int, float))
                                        or isinstance(elapsed, bool) or elapsed < 0):
                findings.append(Finding("L1", "error",
                                        "tool_output elapsed_seconds must be a number >= 0", cid))
            commit, ev_commit = to.get("commit"), ev.get("commit")
            rr = ev.get("run_record") if isinstance(ev.get("run_record"), dict) else {}
            cited = ev_commit or rr.get("commit")
            if commit is not None and not re.match(r"^[0-9a-f]{7,64}$", str(commit)):
                findings.append(Finding("L1", "error",
                                        "tool_output commit is not a git commit hash", cid))
            elif commit and cited and str(commit) != str(cited):
                findings.append(Finding("L1", "error",
                                        "tool_output commit %s does not match evidence commit %s"
                                        % (commit, cited), cid))
            if to.get("command") and ev.get("command") and to["command"] != ev["command"]:
                findings.append(Finding("L1", "error",
                                        "tool_output command does not match evidence command", cid))


def check_sanitizer_runs_schema(claims, findings):
    """L1 shape for evidence.sanitizer_runs (V2-35).

    A sanitizer run is dynamic test evidence attached to kind=test: it says
    which sanitizer instrumented the build, with which flags, over which
    captured output. The shape has to hold before L2 can hash the output and
    compare it with what the record claims.
    """
    for c in claims:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("sanitizer_runs") is None:
                continue
            cid = c["id"]
            runs = ev.get("sanitizer_runs")
            if ev.get("kind") != "test":
                findings.append(Finding("L1", "error",
                                        "sanitizer_runs is only valid on kind=test evidence", cid))
                continue
            if not isinstance(runs, list) or not runs:
                findings.append(Finding("L1", "error",
                                        "sanitizer_runs must be a non-empty list", cid))
                continue
            for k, run in enumerate(runs):
                if not isinstance(run, dict):
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] is not an object" % k, cid))
                    continue
                missing = [f for f in SANITIZER_FIELDS if f not in run]
                if missing:
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] missing %s"
                                            % (k, ", ".join(missing)), cid))
                if run.get("tool") not in SANITIZER_TOOLS:
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] tool %r is not one of %s"
                                            % (k, run.get("tool"), "/".join(SANITIZER_TOOLS)), cid))
                for field in ("build_flags", "command", "output"):
                    value = run.get(field)
                    if not isinstance(value, str) or not value.strip():
                        findings.append(Finding("L1", "error",
                                                "sanitizer_runs[%d] %s must be a non-empty string"
                                                % (k, field), cid))
                sha = run.get("output_sha256")
                if not isinstance(sha, str) or not SHA256_RE.match(sha):
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] output_sha256 is not a sha256 "
                                            "hex digest" % k, cid))
                if not isinstance(run.get("exit_code"), int):
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] exit_code must be an integer" % k, cid))
                for field in ("started_at", "finished_at"):
                    value = run.get(field)
                    if value is not None and _parse_iso(value) is None:
                        findings.append(Finding("L1", "error",
                                                "sanitizer_runs[%d] %s is not an ISO 8601 timestamp"
                                                % (k, field), cid))
                if run.get("status") not in TOOL_RUN_STATUSES:
                    findings.append(Finding("L1", "error",
                                            "sanitizer_runs[%d] status=%r is not one of %s"
                                            % (k, run.get("status"),
                                               ", ".join(TOOL_RUN_STATUSES)), cid))


def check_static_analysis_runs_schema(claims, findings):
    """L1 shape for evidence.static_analysis_runs (V2-36).

    A static-analysis run is a `static-refinement` evidence channel: the engine,
    the rule set it interpreted, the target commit, the raw SARIF, the
    normalized report, and one triage entry per finding. The shape has to hold
    before L2 can hash the artifacts, compare the report with the triage and
    resolve the cells.
    """
    for c in claims:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("static_analysis_runs") is None:
                continue
            cid = c["id"]
            runs = ev.get("static_analysis_runs")
            if ev.get("kind") != "static-analysis":
                findings.append(Finding("L1", "error",
                                        "static_analysis_runs is only valid on "
                                        "kind=static-analysis evidence", cid))
                continue
            if not isinstance(runs, list) or not runs:
                findings.append(Finding("L1", "error",
                                        "static_analysis_runs must be a non-empty list", cid))
                continue
            for k, run in enumerate(runs):
                tag = "static_analysis_runs[%d]" % k
                if not isinstance(run, dict):
                    findings.append(Finding("L1", "error", "%s is not an object" % tag, cid))
                    continue
                missing = [f for f in STATIC_ANALYSIS_FIELDS if f not in run]
                if missing:
                    findings.append(Finding("L1", "error",
                                            "%s missing %s" % (tag, ", ".join(missing)), cid))
                for field in ("tool", "command", "output", "report"):
                    value = run.get(field)
                    if not isinstance(value, str) or not value.strip():
                        findings.append(Finding("L1", "error",
                                                "%s %s must be a non-empty string"
                                                % (tag, field), cid))
                version = run.get("version")
                if version is not None and (not isinstance(version, str)
                                            or not version.strip()):
                    findings.append(Finding("L1", "error",
                                            "%s version must be a non-empty string"
                                            % tag, cid))
                rules = run.get("rules")
                if not isinstance(rules, dict):
                    findings.append(Finding("L1", "error", "%s rules is not an object" % tag, cid))
                else:
                    for field in ("name", "source"):
                        value = rules.get(field)
                        if not isinstance(value, str) or not value.strip():
                            findings.append(Finding("L1", "error",
                                                    "%s rules.%s must be a non-empty string"
                                                    % (tag, field), cid))
                    if not isinstance(rules.get("sha256"), str) \
                            or not SHA256_RE.match(str(rules.get("sha256"))):
                        findings.append(Finding("L1", "error",
                                                "%s rules.sha256 is not a sha256 hex digest"
                                                % tag, cid))
                commit = run.get("target_commit")
                if not isinstance(commit, str) \
                        or not re.match(r"^[0-9a-f]{7,64}$", commit):
                    findings.append(Finding("L1", "error",
                                            "%s target_commit is not a git commit hash"
                                            % tag, cid))
                else:
                    ev_commit = ev.get("commit")
                    if ev_commit and str(commit) != str(ev_commit):
                        findings.append(Finding("L1", "error",
                                                "%s target_commit %s does not match evidence "
                                                "commit %s" % (tag, commit, ev_commit), cid))
                for field in ("output_sha256", "report_sha256"):
                    value = run.get(field)
                    if not isinstance(value, str) or not SHA256_RE.match(value):
                        findings.append(Finding("L1", "error",
                                                "%s %s is not a sha256 hex digest"
                                                % (tag, field), cid))
                if not isinstance(run.get("exit_code"), int):
                    findings.append(Finding("L1", "error",
                                            "%s exit_code must be an integer" % tag, cid))
                for field in ("started_at", "finished_at"):
                    value = run.get(field)
                    if value is not None and _parse_iso(value) is None:
                        findings.append(Finding("L1", "error",
                                                "%s %s is not an ISO 8601 timestamp"
                                                % (tag, field), cid))
                if run.get("status") not in TOOL_RUN_STATUSES:
                    findings.append(Finding("L1", "error",
                                            "%s status=%r is not one of %s"
                                            % (tag, run.get("status"),
                                               ", ".join(TOOL_RUN_STATUSES)), cid))
                if run.get("command") and ev.get("command") \
                        and run["command"] != ev["command"]:
                    findings.append(Finding("L1", "error",
                                            "%s command does not match evidence command"
                                            % tag, cid))
                cells = run.get("cells")
                if cells is not None and (not isinstance(cells, str) or not cells.strip()):
                    findings.append(Finding("L1", "error",
                                            "%s cells must be a non-empty string"
                                            % tag, cid))
                triage = run.get("triage")
                if not isinstance(triage, list):
                    findings.append(Finding("L1", "error", "%s triage is not a list" % tag, cid))
                    continue
                seen = set()
                needs_registry = False
                for j, entry in enumerate(triage):
                    etag = "%s.triage[%d]" % (tag, j)
                    if not isinstance(entry, dict):
                        findings.append(Finding("L1", "error", "%s is not an object" % etag, cid))
                        continue
                    for field in ("finding", "disposition", "date"):
                        if field not in entry:
                            findings.append(Finding("L1", "error",
                                                    "%s missing '%s'" % (etag, field), cid))
                    fid = entry.get("finding")
                    if fid is not None and (not isinstance(fid, str)
                                            or not FINDING_ID_RE.match(fid)):
                        findings.append(Finding("L1", "error",
                                                "%s finding %r does not match ^F-[0-9]{3,}$"
                                                % (etag, fid), cid))
                    elif isinstance(fid, str):
                        if fid in seen:
                            findings.append(Finding("L1", "error",
                                                    "%s duplicates triage for finding %s"
                                                    % (tag, fid), cid))
                        seen.add(fid)
                    disposition = entry.get("disposition")
                    if disposition is not None and disposition not in TRIAGE_DISPOSITIONS:
                        findings.append(Finding("L1", "error",
                                                "%s disposition %r is not one of %s"
                                                % (etag, disposition,
                                                   ", ".join(TRIAGE_DISPOSITIONS)), cid))
                        continue
                    if "date" in entry:
                        date_value = entry.get("date")
                        if not isinstance(date_value, str) \
                                or not DATE_RE.match(date_value) \
                                or _parse_iso(date_value) is None:
                            findings.append(Finding("L1", "error",
                                                    "%s date is not YYYY-MM-DD" % etag, cid))
                    if disposition in TRIAGE_ROUTED:
                        needs_registry = True
                        for field in ("cell", "detector", "fixture"):
                            value = entry.get(field)
                            if not isinstance(value, str) or not value.strip():
                                findings.append(Finding("L1", "error",
                                                        "%s disposition %s requires %s"
                                                        % (etag, disposition, field), cid))
                        cell = entry.get("cell")
                        if isinstance(cell, str) and cell \
                                and not CELL_ID_RE.match(cell):
                            findings.append(Finding("L1", "error",
                                                    "%s cell %r does not match ^CELL-[0-9]{3,}$"
                                                    % (etag, cell), cid))
                        fixture = entry.get("fixture")
                        if isinstance(fixture, str) and fixture and "#" not in fixture:
                            findings.append(Finding("L1", "error",
                                                    "%s fixture %r must use the path#MUT-ID form"
                                                    % (etag, fixture), cid))
                    elif disposition in ("not-a-bug", "out-of-scope"):
                        reason = entry.get("reason")
                        if not isinstance(reason, str) or not reason.strip():
                            findings.append(Finding("L1", "error",
                                                    "%s disposition %s requires a non-empty reason"
                                                    % (etag, disposition), cid))
                    note = entry.get("note")
                    if note is not None and not isinstance(note, str):
                        findings.append(Finding("L1", "error",
                                                "%s note must be a string" % etag, cid))
                anchor = run.get("anchor")
                if not isinstance(anchor, dict):
                    findings.append(Finding("L1", "error",
                                            "%s anchor is not an object; every static-analysis "
                                            "run must carry an anchor (C-13)" % tag, cid))
                else:
                    missing_anchor = [f for f in ANCHOR_FIELDS if f not in anchor]
                    if missing_anchor:
                        findings.append(Finding("L1", "error",
                                                "%s anchor missing %s"
                                                % (tag, ", ".join(missing_anchor)), cid))
                    if anchor.get("type") not in ANCHOR_TYPES:
                        findings.append(Finding("L1", "error",
                                                "%s anchor.type=%r is not one of %s"
                                                % (tag, anchor.get("type"),
                                                   ", ".join(ANCHOR_TYPES)), cid))
                    for field in ("signer", "namespace", "subject", "signature",
                                  "allowed_signers"):
                        value = anchor.get(field)
                        if not isinstance(value, str) or not value.strip():
                            findings.append(Finding("L1", "error",
                                                    "%s anchor.%s must be a non-empty string"
                                                    % (tag, field), cid))
                    for field in ("subject_sha256", "signature_sha256"):
                        value = anchor.get(field)
                        if not isinstance(value, str) or not SHA256_RE.match(value):
                            findings.append(Finding("L1", "error",
                                                    "%s anchor.%s is not a sha256 hex digest"
                                                    % (tag, field), cid))
                    anchor_date = anchor.get("date")
                    if not isinstance(anchor_date, str) \
                            or not DATE_RE.match(anchor_date) \
                            or _parse_iso(anchor_date) is None:
                        findings.append(Finding("L1", "error",
                                                "%s anchor.date is not YYYY-MM-DD" % tag, cid))
                if needs_registry and not run.get("cells"):
                    findings.append(Finding("L1", "error",
                                            "%s triage routes a finding to a cell but the run "
                                            "names no cells registry" % tag, cid))


# ------------------------------------------------------- L2 evidence health

def _check_run_record(ev, rr, claim, root, run_log_root, log_cache, findings):
    cid = claim["id"]
    status = claim.get("status")

    if isinstance(rr.get("exit_code"), int) and rr["exit_code"] != 0 and status != "open":
        findings.append(Finding("L2", "error",
                                "run_record exit_code=%s cannot support status=%s"
                                % (rr["exit_code"], status), cid))

    start, end = _parse_iso(rr.get("started_at")), _parse_iso(rr.get("finished_at"))
    if start and end:
        if start > end:
            findings.append(Finding("L2", "error",
                                    "run_record started_at is after finished_at", cid))
        ev_date = ev.get("date")
        if ev_date and DATE_RE.match(str(ev_date)) and end.date().isoformat() != str(ev_date):
            findings.append(Finding("L2", "error",
                                    "run_record finished_at date %s does not match evidence date %s"
                                    % (end.date().isoformat(), ev_date), cid))

    text = None
    log = rr.get("log")
    if log:
        if URL_RE.match(str(log)):
            findings.append(Finding("L2", "info",
                                    "run_record log is a URL; its hash is not checked", cid))
        else:
            path = str(log) if os.path.isabs(str(log)) else os.path.join(run_log_root, str(log))
            if not os.path.exists(path):
                findings.append(Finding("L2", "error", "run_record log not found: %s" % log, cid))
            else:
                actual = _sha256_file(path)
                if rr.get("log_sha256") and actual != rr["log_sha256"]:
                    findings.append(Finding("L2", "error",
                                            "run_record log_sha256 mismatch for %s" % log, cid))
                if path not in log_cache:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        log_cache[path] = f.read()
                text = log_cache[path]

    artifact = ev.get("artifact")
    if artifact and rr.get("artifact_sha256"):
        if URL_RE.match(artifact):
            findings.append(Finding("L2", "info",
                                    "artifact is a URL; its sha256 is not checked", cid))
        else:
            p = os.path.join(root, artifact)
            if os.path.exists(p) and _sha256_file(p) != rr["artifact_sha256"]:
                findings.append(Finding("L2", "error",
                                        "run_record artifact_sha256 mismatch for %s" % artifact, cid))

    if text is not None:
        for tid in ev.get("tests") or []:
            if not _test_ran(tid, text):
                findings.append(Finding("L2", "error",
                                        "test %r is cited but not executed in the run log" % tid, cid))
        summary = _log_summary(text)
        if summary is None:
            findings.append(Finding("L2", "info",
                                    "run log has no recognizable summary; counts not cross-checked", cid))
        else:
            passed, failed = summary
            tr, tp = rr.get("tests_run"), rr.get("tests_passed")
            if isinstance(tr, int) and isinstance(tp, int) and (passed + failed != tr or passed != tp):
                findings.append(Finding("L2", "error",
                                        "run_record counts (%d run, %d passed) disagree with log (%d run, %d passed)"
                                        % (tr, tp, passed + failed, passed), cid))
            rc = rr.get("exit_code")
            if isinstance(rc, int) and ((rc == 0) != (failed == 0)):
                findings.append(Finding("L2", "error",
                                        "run_record exit_code=%d disagrees with the log's %d failed test(s)"
                                        % (rc, failed), cid))


def _check_tool_output(ev, to, claim, tool_output_root, findings):
    """L2: the tool output exists, matches its hash, and supports the status."""
    cid = claim["id"]
    status = claim.get("status")

    rc = to.get("exit_code")
    if isinstance(rc, int) and rc != 0 and status != "open":
        findings.append(Finding("L2", "error",
                                "tool_output exit_code=%d cannot support status=%s"
                                % (rc, status), cid))

    # V2-28: only a completed run can support a non-open claim. A timeout, a
    # failure to start or a tool that gave up is `unverified`, not a pass with
    # a short log.
    run_status = to.get("status")
    if run_status in TOOL_RUN_STATUSES and run_status != "completed" \
            and status != "open":
        findings.append(Finding("L2", "error",
                                "tool_output status=%s cannot support status=%s (V2-28)"
                                % (run_status, status), cid))
    if to.get("timed_out") is True and status != "open":
        findings.append(Finding("L2", "error",
                                "a timed-out tool_output cannot support status=%s (V2-28)"
                                % status, cid))

    start, end = _parse_iso(to.get("started_at")), _parse_iso(to.get("finished_at"))
    if start and end:
        if start > end:
            findings.append(Finding("L2", "error",
                                    "tool_output started_at is after finished_at", cid))
        ev_date = ev.get("date")
        if ev_date and DATE_RE.match(str(ev_date)) and end.date().isoformat() != str(ev_date):
            findings.append(Finding("L2", "error",
                                    "tool_output finished_at date %s does not match evidence date %s"
                                    % (end.date().isoformat(), ev_date), cid))

    output = to.get("output")
    if not isinstance(output, str) or not output:
        return
    if URL_RE.match(output):
        findings.append(Finding("L2", "info",
                                "tool_output output is a URL; its hash is not checked", cid))
        return
    path = output if os.path.isabs(output) else os.path.join(tool_output_root, output)
    if not os.path.exists(path):
        findings.append(Finding("L2", "error",
                                "tool_output output not found: %s" % output, cid))
        return
    actual = _sha256_file(path)
    if actual != to.get("output_sha256"):
        findings.append(Finding("L2", "error",
                                "tool_output output_sha256 mismatch for %s" % output, cid))


def _check_sanitizer_run(ev, run, claim, tool_output_root, index, findings):
    """L2: the sanitizer's own captured output supports what the record says.

    A sanitizer run is dynamic evidence: it can only disprove a claim about
    memory or undefined behaviour. The record therefore has to show that the
    instrumented build actually ran to completion, and its bytes must agree
    with the declared outcome. The strongest local check is the contradiction
    between a clean record (completed, exit 0) and a finding line in the
    output it cites.
    """
    cid = claim["id"]
    status = claim.get("status")
    tag = "sanitizer_runs[%d]" % index

    rc = run.get("exit_code")
    if isinstance(rc, int) and rc != 0 and status != "open":
        findings.append(Finding("L2", "error",
                                "%s exit_code=%d cannot support status=%s"
                                % (tag, rc, status), cid))

    # Same vocabulary as tool_output (V2-28): only a completed run can support
    # a non-open claim. A cut-short run is unverified, not a pass.
    run_status = run.get("status")
    if run_status in TOOL_RUN_STATUSES and run_status != "completed" \
            and status != "open":
        findings.append(Finding("L2", "error",
                                "%s status=%s cannot support status=%s (V2-28)"
                                % (tag, run_status, status), cid))

    start, end = _parse_iso(run.get("started_at")), _parse_iso(run.get("finished_at"))
    if start and end:
        if start > end:
            findings.append(Finding("L2", "error",
                                    "%s started_at is after finished_at" % tag, cid))
        ev_date = ev.get("date")
        if ev_date and DATE_RE.match(str(ev_date)) and end.date().isoformat() != str(ev_date):
            findings.append(Finding("L2", "error",
                                    "%s finished_at date %s does not match evidence date %s"
                                    % (tag, end.date().isoformat(), ev_date), cid))

    output = run.get("output")
    if not isinstance(output, str) or not output:
        return
    if URL_RE.match(output):
        findings.append(Finding("L2", "info",
                                "%s output is a URL; its hash is not checked" % tag, cid))
        return
    path = output if os.path.isabs(output) else os.path.join(tool_output_root, output)
    if not os.path.exists(path):
        findings.append(Finding("L2", "error",
                                "%s output not found: %s" % (tag, output), cid))
        return
    if _sha256_file(path) != run.get("output_sha256"):
        findings.append(Finding("L2", "error",
                                "%s output_sha256 mismatch for %s" % (tag, output), cid))
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    # A sanitizer that halts prints a finding line. A record that declares a
    # clean run over such output contradicts the bytes it cites: either the run
    # did not finish cleanly or the record hides the finding.
    if run_status == "completed" and rc == 0 and SANITIZER_FINDING_RE.search(text):
        findings.append(Finding("L2", "error",
                                "%s declares a clean run (status=completed, exit_code=0) but "
                                "its output carries a sanitizer finding line" % tag, cid))


def _load_structured(path):
    """Load a JSON or YAML file (the cell registries and fixtures are YAML)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise ValueError("PyYAML is required for %s" % path)
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _registry_cells(path):
    doc = _load_structured(path)
    if not isinstance(doc, dict) or not isinstance(doc.get("cells"), list):
        raise ValueError("registry has no cells list: %s" % path)
    return {c.get("id"): c for c in doc["cells"] if isinstance(c, dict)}


def _fixture_ids(path):
    """Fixture IDs of a mutation file.

    The two pilots name the list differently (`mutations` and `fixtures`), and
    the cell registry points at either by `path#MUT-ID`.
    """
    doc = _load_structured(path)
    if not isinstance(doc, dict):
        return set()
    items = doc.get("fixtures")
    if not isinstance(items, list):
        items = doc.get("mutations")
    if not isinstance(items, list):
        return set()
    return {item.get("id") for item in items if isinstance(item, dict)}


def _check_anchor(run, claim, tool_output_root, tag, findings):
    """L2: the signature covers the record, not some other bytes.

    The signed subject is a canonical function of the run (engine, command,
    rules, commit, both hashes, exit code, timestamps, status and triage). L2
    recomputes it and compares, then asks ssh-keygen to verify the signature
    against the committed allowed_signers. An editor who changes a finding's
    disposition, a hash or a timestamp without the private key cannot make both
    checks pass. The key holder, or anyone who can replace allowed_signers and
    re-sign, still can; that is the C-13 gap the docs state.
    """
    cid = claim["id"]
    status = claim.get("status")
    anchor = run.get("anchor")
    if not isinstance(anchor, dict):
        return  # L1 already reported the missing shape

    def resolve(value):
        if not isinstance(value, str) or not value.strip():
            return None
        return value if os.path.isabs(value) else os.path.join(tool_output_root, value)

    subject_path = resolve(anchor.get("subject"))
    signature_path = resolve(anchor.get("signature"))
    allowed_path = resolve(anchor.get("allowed_signers"))
    for label, value, path in (
            ("subject", anchor.get("subject"), subject_path),
            ("signature", anchor.get("signature"), signature_path),
            ("allowed_signers", anchor.get("allowed_signers"), allowed_path)):
        if path is None or not os.path.exists(path):
            findings.append(Finding("L2", "error",
                                    "%s anchor %s not found: %s" % (tag, label, value), cid))
            return

    if _sha256_file(subject_path) != anchor.get("subject_sha256"):
        findings.append(Finding("L2", "error",
                                "%s anchor subject_sha256 mismatch for %s"
                                % (tag, anchor.get("subject")), cid))
    if _sha256_file(signature_path) != anchor.get("signature_sha256"):
        findings.append(Finding("L2", "error",
                                "%s anchor signature_sha256 mismatch for %s"
                                % (tag, anchor.get("signature")), cid))

    expected = anchor_subject.subject_bytes(run)
    actual = open(subject_path, "rb").read()
    if actual != expected:
        findings.append(Finding("L2", "error",
                                "%s anchor subject does not describe this record; a signed "
                                "field changed after signing" % tag, cid))

    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        severity = "error" if status != "open" else "info"
        findings.append(Finding("L2", severity,
                                "%s anchor cannot be verified: ssh-keygen is not on PATH"
                                % tag, cid))
        return
    proc = subprocess.run(
        [ssh_keygen, "-Y", "verify", "-f", allowed_path,
         "-I", str(anchor.get("signer", "")), "-n", str(anchor.get("namespace", "")),
         "-s", signature_path],
        input=expected, capture_output=True)
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
        first = detail.splitlines()[0] if detail else "ssh-keygen returned %d" % proc.returncode
        findings.append(Finding("L2", "error",
                                "%s anchor signature does not verify: %s" % (tag, first), cid))


def _check_static_analysis_run(ev, run, claim, root, tool_output_root, index, findings):
    """L2: the engine output, the report and the triage support the record.

    A static-analysis run is a review-queue producer, not a verdict. The record
    has to show that the run completed, that both outputs hash to the cited
    bytes, that the normalized report hashes the same SARIF, that no finding is
    unclassified or authored, and that every finding in the report has exactly
    one disposition which resolves when it names a cell.
    """
    cid = claim["id"]
    status = claim.get("status")
    tag = "static_analysis_runs[%d]" % index

    rc = run.get("exit_code")
    if isinstance(rc, int) and rc != 0 and status != "open":
        findings.append(Finding("L2", "error",
                                "%s exit_code=%d cannot support status=%s"
                                % (tag, rc, status), cid))

    run_status = run.get("status")
    if run_status in TOOL_RUN_STATUSES and run_status != "completed" \
            and status != "open":
        findings.append(Finding("L2", "error",
                                "%s status=%s cannot support status=%s (V2-28)"
                                % (tag, run_status, status), cid))

    start, end = _parse_iso(run.get("started_at")), _parse_iso(run.get("finished_at"))
    if start and end:
        if start > end:
            findings.append(Finding("L2", "error",
                                    "%s started_at is after finished_at" % tag, cid))
        ev_date = ev.get("date")
        if ev_date and DATE_RE.match(str(ev_date)) and end.date().isoformat() != str(ev_date):
            findings.append(Finding("L2", "error",
                                    "%s finished_at date %s does not match evidence date %s"
                                    % (tag, end.date().isoformat(), ev_date), cid))

    # The target commit is what makes the findings about the cited bytes. A
    # checkout that no longer resolves the commit is a different target.
    commit = run.get("target_commit")
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if isinstance(commit, str) and commit \
            and inside.returncode == 0 and inside.stdout.strip() == "true":
        if _git(root, "cat-file", "-e", "%s^{commit}" % commit).returncode != 0:
            findings.append(Finding("L2", "error",
                                    "%s target_commit %s is not resolvable in %s"
                                    % (tag, commit, root), cid))

    # The rule bytes decide what the engine could find; hash them locally.
    rules = run.get("rules") if isinstance(run.get("rules"), dict) else {}
    source = rules.get("source")
    if isinstance(source, str) and source:
        if URL_RE.match(source):
            findings.append(Finding("L2", "info",
                                    "%s rules.source is a URL; its hash is not checked"
                                    % tag, cid))
        else:
            path = source if os.path.isabs(source) \
                else os.path.join(tool_output_root, source)
            if not os.path.exists(path):
                findings.append(Finding("L2", "error",
                                        "%s rules file not found: %s" % (tag, source), cid))
            elif _sha256_file(path) != rules.get("sha256"):
                findings.append(Finding("L2", "error",
                                        "%s rules.sha256 mismatch for %s"
                                        % (tag, source), cid))

    # The anchor is checked before the output paths: a URL output can return
    # early, but the signature still has to describe this record.
    _check_anchor(run, claim, tool_output_root, tag, findings)

    # Raw output: the bytes the engine wrote.
    output = run.get("output")
    if not isinstance(output, str) or not output:
        return
    if URL_RE.match(output):
        # The hash is the only link between the record and the bytes. A remote
        # output cannot be hashed here, so it cannot support a non-open claim.
        severity = "error" if status != "open" else "info"
        findings.append(Finding("L2", severity,
                                "%s output is a URL; its hash is not checked and it "
                                "cannot support status=%s" % (tag, status), cid))
    else:
        output_path = output if os.path.isabs(output) \
            else os.path.join(tool_output_root, output)
        if not os.path.exists(output_path):
            findings.append(Finding("L2", "error",
                                    "%s output not found: %s" % (tag, output), cid))
            return
        if _sha256_file(output_path) != run.get("output_sha256"):
            findings.append(Finding("L2", "error",
                                    "%s output_sha256 mismatch for %s"
                                    % (tag, output), cid))

    # Normalized report: the finding identities the triage names.
    report = None
    report_ref = run.get("report")
    if not isinstance(report_ref, str) or not report_ref:
        return
    if URL_RE.match(report_ref):
        # The triage names findings by the report's ids, and the report hashes
        # the SARIF. Without local report bytes the bijection cannot be checked,
        # so a URL report is not evidence for a non-open claim.
        severity = "error" if status != "open" else "info"
        findings.append(Finding("L2", severity,
                                "%s report is a URL; its hash and triage cannot be "
                                "checked and it cannot support status=%s"
                                % (tag, status), cid))
        return
    report_path = report_ref if os.path.isabs(report_ref) \
        else os.path.join(tool_output_root, report_ref)
    if not os.path.exists(report_path):
        findings.append(Finding("L2", "error",
                                "%s report not found: %s" % (tag, report_ref), cid))
        return
    if _sha256_file(report_path) != run.get("report_sha256"):
        findings.append(Finding("L2", "error",
                                "%s report_sha256 mismatch for %s"
                                % (tag, report_ref), cid))
    try:
        report = _load_structured(report_path)
    except (OSError, ValueError) as e:
        findings.append(Finding("L2", "error",
                                "%s report is not readable JSON/YAML: %s" % (tag, e), cid))
        return
    if not isinstance(report, dict):
        findings.append(Finding("L2", "error", "%s report is not an object" % tag, cid))
        return

    if report.get("format") != STATIC_REPORT_FORMAT:
        findings.append(Finding("L2", "error",
                                "%s report format is %r, expected %r"
                                % (tag, report.get("format"), STATIC_REPORT_FORMAT), cid))
    inputs = [i.get("sha256") for i in report.get("inputs") or []
              if isinstance(i, dict)]
    if run.get("output_sha256") not in inputs:
        findings.append(Finding("L2", "error",
                                "%s report does not hash the cited output as an input"
                                % tag, cid))

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for key in ("unmapped", "fixture_inputs"):
        value = summary.get(key)
        if not isinstance(value, int):
            findings.append(Finding("L2", "error",
                                    "%s report summary.%s is missing or not an integer"
                                    % (tag, key), cid))
        elif value != 0:
            severity = "error" if status != "open" else "warning"
            findings.append(Finding("L2", severity,
                                    "%s report summary.%s=%d: an unclassified or authored "
                                    "input cannot support status=%s"
                                    % (tag, key, value, status), cid))

    # The engine the record names must be the engine that produced the
    # findings, not merely a name in the configuration file.
    tool = run.get("tool")
    tool_key = str(tool).strip().lower() if isinstance(tool, str) else ""
    engines = [e for e in report.get("engines") or []
               if isinstance(e, dict) and e.get("runs")]
    if not any(tool_key == str(e.get("id", "")).lower()
               or tool_key == str(e.get("name", "")).lower()
               for e in engines):
        findings.append(Finding("L2", "error",
                                "%s tool %r is not a present engine in the report"
                                % (tag, tool), cid))

    # Bijection between report findings and triage entries.
    report_findings = [f for f in report.get("findings") or [] if isinstance(f, dict)]
    ids = [f.get("id") for f in report_findings]
    if any(not isinstance(fid, str) or not FINDING_ID_RE.match(fid) for fid in ids):
        findings.append(Finding("L2", "error",
                                "%s report has a finding without an F-NNN id" % tag, cid))
        return
    triage = [t for t in run.get("triage") or [] if isinstance(t, dict)]
    seen = set()
    for entry in triage:
        fid = entry.get("finding")
        if fid not in ids:
            findings.append(Finding("L2", "error",
                                    "%s triage names finding %r that is not in the report"
                                    % (tag, fid), cid))
            continue
        if fid in seen:
            findings.append(Finding("L2", "error",
                                    "%s has more than one triage entry for finding %s"
                                    % (tag, fid), cid))
            continue
        seen.add(fid)
    missing = sorted(set(ids) - seen)
    if missing:
        findings.append(Finding("L2", "error",
                                "%s finding(s) %s have no triage entry"
                                % (tag, ", ".join(missing)), cid))

    # Routing: a covered/new entry names a cell, a detector of that cell and a
    # fixture that holds the cited mutation. A not-a-bug/out-of-scope entry is
    # its reason; L1 already required one.
    routed = [e for e in triage if e.get("disposition") in TRIAGE_ROUTED]
    if not routed:
        return
    declared = run.get("cells")
    if not declared:
        findings.append(Finding("L2", "error",
                                "%s routes a finding to a cell but names no registry"
                                % tag, cid))
        return
    cells_path = declared if os.path.isabs(declared) \
        else os.path.join(tool_output_root, declared)
    if not os.path.exists(cells_path):
        findings.append(Finding("L2", "error",
                                "%s cell registry not found: %s" % (tag, declared), cid))
        return
    try:
        cells = _registry_cells(cells_path)
    except (OSError, ValueError) as e:
        findings.append(Finding("L2", "error",
                                "%s cannot load cell registry: %s" % (tag, e), cid))
        return
    for entry in routed:
        who = "%s finding %s" % (tag, entry.get("finding"))
        cell_id = entry.get("cell")
        cell = cells.get(cell_id)
        if cell is None:
            findings.append(Finding("L2", "error",
                                    "%s: cell %r is not in %s"
                                    % (who, cell_id, declared), cid))
            continue
        detectors = [d.get("id") for d in cell.get("detectors") or []
                     if isinstance(d, dict)]
        if entry.get("detector") not in detectors:
            findings.append(Finding("L2", "error",
                                    "%s: detector %r is not in cell %s"
                                    % (who, entry.get("detector"), cell_id), cid))
        fixture = entry.get("fixture")
        if not isinstance(fixture, str) or "#" not in fixture:
            continue
        rel, fixture_id = fixture.rsplit("#", 1)
        fixture_path = rel if os.path.isabs(rel) else os.path.join(tool_output_root, rel)
        if not os.path.exists(fixture_path):
            findings.append(Finding("L2", "error",
                                    "%s: fixture file not found: %s" % (who, rel), cid))
            continue
        try:
            fixture_ids = _fixture_ids(fixture_path)
        except (OSError, ValueError) as e:
            findings.append(Finding("L2", "error",
                                    "%s: cannot load fixture file %s: %s"
                                    % (who, rel, e), cid))
            continue
        if fixture_id not in fixture_ids:
            findings.append(Finding("L2", "error",
                                    "%s: fixture %r is not in %s"
                                    % (who, fixture_id, rel), cid))


def _git(root, *args):
    return subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True)


def _artifact_at_commit(root, commit, artifact):
    """Compare the working-tree artifact with its blob at the cited commit.

    Returns "ok", "missing" (the commit does not contain the path), "differs"
    (the bytes changed after the commit), or None when the root is not inside a
    git work tree, which is the case for the synthetic eval fixtures.
    """
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    prefix = _git(root, "rev-parse", "--show-prefix").stdout.strip()
    path = prefix + artifact
    if _git(root, "cat-file", "-e", "%s:%s" % (commit, path)).returncode != 0:
        return "missing"
    diff = _git(root, "diff", "--quiet", commit, "--", path)
    if diff.returncode == 1:
        return "differs"
    if diff.returncode != 0:
        return None
    return "ok"


def check_evidence(claims, root, max_age_days, findings, run_log_root=None,
                   tool_output_root=None):
    run_log_root = run_log_root or root
    tool_output_root = tool_output_root or root
    today = date.today()
    log_cache = {}
    for c in claims:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            artifact = ev.get("artifact")
            if artifact and not re.match(r"^[a-z]+://", artifact):
                p = os.path.join(root, artifact)
                if not os.path.exists(p):
                    findings.append(Finding("L2", "error", "artifact not found: %s" % artifact, c["id"]))
            rr = ev.get("run_record") if isinstance(ev.get("run_record"), dict) else {}
            commit = ev.get("commit") or rr.get("commit")
            if commit:
                r = subprocess.run(
                    ["git", "cat-file", "-e", "%s^{commit}" % commit],
                    cwd=root, capture_output=True)
                if r.returncode != 0:
                    findings.append(Finding("L2", "error", "commit not resolvable: %s" % commit, c["id"]))
                elif artifact and not re.match(r"^[a-z]+://", artifact):
                    state = _artifact_at_commit(root, commit, artifact)
                    if state == "missing":
                        findings.append(Finding("L2", "error",
                                                "artifact %s does not exist at the cited commit %s"
                                                % (artifact, str(commit)[:12]), c["id"]))
                    elif state == "differs":
                        findings.append(Finding("L2", "error",
                                                "artifact %s changed after the cited commit %s; the "
                                                "evidence describes different bytes"
                                                % (artifact, str(commit)[:12]), c["id"]))
            when = ev.get("date") or c.get("last_verified")
            if when:
                if not DATE_RE.match(str(when)):
                    findings.append(Finding("L2", "warning", "date %r is not YYYY-MM-DD" % when, c["id"]))
                else:
                    d = datetime.strptime(str(when), "%Y-%m-%d").date()
                    if d > today:
                        findings.append(Finding("L2", "warning", "evidence dated in the future: %s" % d, c["id"]))
                    elif (today - d).days > max_age_days:
                        findings.append(Finding("L2", "warning",
                                                "stale evidence: %s (%d days old, window %d)"
                                                % (d, (today - d).days, max_age_days), c["id"]))
            if ev.get("kind") == "test" and ev.get("run_record") is None:
                findings.append(Finding("L2", "warning",
                                        "kind=test has no run_record: re-dating and a cited test "
                                        "that never ran are not detectable (V2-02)", c["id"]))
            elif isinstance(ev.get("run_record"), dict):
                _check_run_record(ev, ev["run_record"], c, root, run_log_root,
                                  log_cache, findings)
            if isinstance(ev.get("tool_output"), dict):
                _check_tool_output(ev, ev["tool_output"], c, tool_output_root, findings)
            if isinstance(ev.get("sanitizer_runs"), list):
                for k, run in enumerate(ev["sanitizer_runs"]):
                    if isinstance(run, dict):
                        _check_sanitizer_run(ev, run, c, tool_output_root, k, findings)
            if isinstance(ev.get("static_analysis_runs"), list):
                for k, run in enumerate(ev["static_analysis_runs"]):
                    if isinstance(run, dict):
                        _check_static_analysis_run(ev, run, c, root,
                                                   tool_output_root, k, findings)


# --------------------------------------------------------- L3 traceability

def build_suite_index(root, suite_glob):
    report_ids, def_names = set(), set()
    for path in walk_files(root, suite_glob):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        report_ids.update(REPORT_ID_RE.findall(text))
        def_names.update(DEF_TEST_RE.findall(text))
        def_names.update(RUST_TEST_RE.findall(text))
    return report_ids, def_names


def id_resolves(tid, report_ids, def_names):
    if tid in report_ids:
        return True
    flat = tid.lower().replace("-", "_").replace(".", "_")
    return any(flat in name for name in def_names)


def check_traceability(claims, report_ids, def_names, findings):
    for c in claims:
        for ev in c.get("evidence") or []:
            if ev.get("kind") != "test":
                continue
            for tid in ev.get("tests") or []:
                if not id_resolves(tid, report_ids, def_names):
                    findings.append(Finding("L3", "error",
                                            "test ID %r not found in suite" % tid, c["id"]))


# ----------------------------------------------------------- L4 consistency

def check_consistency(claims, report_ids, def_names, findings):
    for c in claims:
        kinds = {ev["kind"] for ev in c.get("evidence") or [] if isinstance(ev, dict)}
        status = c.get("status")
        required = STATUS_REQUIRES_KIND.get(status)
        if required and required not in kinds:
            findings.append(Finding("L4", "error",
                                    "status=%s requires evidence kind=%s" % (status, required), c["id"]))
        if status == "tested":
            resolvable = all(
                id_resolves(tid, report_ids, def_names)
                for ev in c.get("evidence") or []
                if isinstance(ev, dict) and ev.get("kind") == "test"
                for tid in ev.get("tests") or [])
            if not resolvable:
                findings.append(Finding("L4", "error",
                                        "status=tested but not every test ID resolves", c["id"]))
        if status == "open" and "test" in kinds:
            findings.append(Finding("L4", "warning",
                                    "status=open but test evidence is listed", c["id"]))
        if "proof" in kinds and status != "proven":
            findings.append(Finding("L4", "warning",
                                    "proof evidence present but status=%s" % status, c["id"]))
        # V2-10: a status that names a tool run needs the tool's own output. An
        # artifact (a .tla or .als file) only proves that a model exists.
        if status in TOOL_STATUSES:
            tool_outputs = [ev.get("tool_output") for ev in c.get("evidence") or []
                            if isinstance(ev, dict) and isinstance(ev.get("tool_output"), dict)]
            if not tool_outputs:
                findings.append(Finding("L4", "error",
                                        "status=%s requires evidence with a tool_output (V2-10)"
                                        % status, c["id"]))
            elif status == "model-checked" and not any(
                    isinstance(t.get("bound"), str) and t["bound"].strip()
                    for t in tool_outputs):
                findings.append(Finding("L4", "error",
                                        "status=model-checked requires a tool_output that states "
                                        "the bound (V2-10)", c["id"]))
        # V2-36: a static-refinement status names an analysis run. A
        # kind=static-analysis evidence item without a record is prose, and
        # prose cannot say which engine ran over which commit with which rules.
        if status == "static-refinement":
            runs = [run for ev in c.get("evidence") or []
                    if isinstance(ev, dict)
                    for run in (ev.get("static_analysis_runs") or [])
                    if isinstance(run, dict)]
            if not runs:
                findings.append(Finding("L4", "error",
                                        "status=static-refinement requires evidence with a "
                                        "static_analysis_runs record (V2-36)", c["id"]))


# ---------------------------------------------------------------- L5 prose

def _line_text(root, rel, line_no):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[line_no - 1] if 0 < line_no <= len(lines) else ""
    except OSError:
        return ""


def _closest_distance(re_obj, line, pos):
    """Distance from pos to the nearest match of re_obj; None if no match."""
    best = None
    for m in re_obj.finditer(line):
        d = min(abs(m.start() - pos), abs(m.end() - pos))
        if best is None or d < best:
            best = d
    return best


def check_prose(root, docs_glob, styles_path, findings):
    """L5: Vale-first, built-in scanner as fallback."""
    vale_bin = find_vale()
    if vale_bin and styles_path and os.path.isdir(styles_path):
        return check_prose_vale(root, docs_glob, vale_bin, styles_path, findings)
    return check_prose_internal(root, docs_glob, findings)


def check_prose_vale(root, docs_glob, vale_bin, styles_path, findings):
    """Run the RussianAbsolutes Vale package over the docs-glob files.

    Only files matching docs_glob are passed (not the whole tree), so the
    Vale run matches the built-in scanner's scope.
    """
    files = sorted(walk_files(root, docs_glob))
    if not files:
        return 0
    # Vale matches sections by path: both the section glob and the file list
    # must be absolute. With a relative root ("."), "[./**]" matched nothing
    # and Vale returned 0 findings silently.
    root_abs = os.path.abspath(root)
    files = [os.path.abspath(f) for f in files]
    try:
        with tempfile.TemporaryDirectory() as td:
            ini = os.path.join(td, ".vale.ini")
            with open(ini, "w", encoding="utf-8") as f:
                f.write(VALE_CONFIG_TEMPLATE.format(styles=styles_path, root=root_abs))
            r = subprocess.run(
                [vale_bin, "--config=" + ini, "--output=JSON"] + files,
                capture_output=True, text=True, timeout=120)
            if r.returncode not in (0, 1):
                raise RuntimeError("vale exited %d: %s" % (r.returncode, r.stderr[:200]))
            data = json.loads(r.stdout or "{}")
    except (OSError, RuntimeError, ValueError) as e:
        findings.append(Finding("L5", "info", "vale unavailable (%s); using built-in scanner" % e))
        return check_prose_internal(root, "*.md", findings)
    count = 0
    for filepath, file_matches in (data or {}).items():
        rel = os.path.relpath(filepath, root)
        for m in file_matches:
            check = m.get("Check", "")
            if not check.startswith("RussianAbsolutes."):
                continue
            severity = "warning" if m.get("Severity") == "warning" else "info"
            line_text = _line_text(root, rel, m.get("Line") or 0)
            # Proximity to the match decides which context applies.
            span = m.get("Span") or []
            pos = span[0] if span else line_text.find(m.get("Match", ""))
            self_d = _closest_distance(SELF_CONTEXT_RE, line_text, pos)
            third_d = _closest_distance(THIRD_PARTY_RE, line_text, pos)
            if third_d is not None and (self_d is None or third_d <= self_d):
                severity = "info"
                note = "third-party context"
            else:
                note = None
            msg = "%s: %s" % (check, m.get("Match", ""))
            if note:
                msg += " (%s)" % note
            findings.append(Finding("L5", severity, msg, None, rel, m.get("Line")))
            count += 1
    return count


def check_prose_internal(root, docs_glob, findings):
    banned_re = re.compile("|".join(BANNED), re.IGNORECASE)
    for path in walk_files(root, docs_glob):
        rel = os.path.relpath(path, root)
        try:
            lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            m = banned_re.search(line)
            if not m:
                continue
            if EVIDENCE_HINT_RE.search(line):
                findings.append(Finding("L5", "info",
                                        "qualified absolute %r" % m.group(0), None, rel, n))
            else:
                findings.append(Finding("L5", "warning",
                                        "unqualified absolute %r" % m.group(0), None, rel, n))


# ------------------------------------------------------- L6 relevance

def _test_owners(claims):
    """Map each cited test ID to the claim IDs that cite it (V2-34)."""
    owners = {}
    for c in claims:
        cid = c.get("id")
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("kind") != "test":
                continue
            for tid in ev.get("tests") or []:
                if isinstance(tid, str):
                    owners.setdefault(tid, set()).add(cid)
    return owners


def _declared_shared(ev):
    """Test IDs declared in one evidence item's shared_tests list."""
    declared = set()
    for entry in ev.get("shared_tests") or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            declared.add(entry["id"])
    return declared


def check_relevance(claims, findings):
    """A cited test must be tied to the claim that cites it (V2-34).

    Two rules, because a declaration alone is cheap:

      1. A test cited by more than one claim must appear in each citing
         claim's `shared_tests` with a reason.
      2. A non-open claim must cite at least one test no other claim cites.
         This stays an error even when the sharing is declared, so moving a
         claim onto a neighbour's test does not inherit the neighbour's
         evidence.
    """
    owners = _test_owners(claims)
    for c in claims:
        cid = c.get("id")
        cited, declared = set(), set()
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("kind") != "test":
                continue
            cited.update(t for t in ev.get("tests") or [] if isinstance(t, str))
            declared.update(_declared_shared(ev))
        shared_here = {t for t in cited if len(owners.get(t, ())) > 1}
        for tid in sorted(shared_here - declared):
            findings.append(Finding(
                "L6", "error",
                "test %r is cited by %s but not declared in shared_tests with a reason (V2-34)"
                % (tid, ", ".join(sorted(owners[tid]))), cid))
        if c.get("status") != "open" and cited and all(
                len(owners.get(t, ())) > 1 for t in cited):
            findings.append(Finding(
                "L6", "error",
                "every cited test is also evidence for another claim; a non-open claim "
                "needs at least one test of its own (V2-34)", cid))


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Claim ledger linter (dev-sec-skills)")
    ap.add_argument("ledger", help="path to ledger (JSON or YAML)")
    ap.add_argument("--root", default=None, help="project root (default: ledger's directory parent)")
    ap.add_argument("--suite-glob", default="*.py", help="glob for suite files (default: *.py)")
    ap.add_argument("--docs-glob", default="*.md", help="glob for prose docs (default: *.md)")
    ap.add_argument("--max-age-days", type=int, default=90)
    ap.add_argument("--run-log-root", default=None,
                    help="directory that run_record.log paths are relative to "
                         "(default: --root)")
    ap.add_argument("--tool-output-root", default=None,
                    help="directory that tool_output.output paths are relative to "
                         "(default: --root)")
    ap.add_argument("--no-vale", action="store_true",
                    help="skip Vale and use the built-in L5 scanner")
    args = ap.parse_args()

    root = args.root or os.path.dirname(os.path.abspath(args.ledger))
    if not os.path.isfile(args.ledger):
        print("ledger not found: %s" % args.ledger, file=sys.stderr)
        return 2
    if not os.path.isdir(root):
        print("root not found: %s" % root, file=sys.stderr)
        return 2

    styles_path = os.environ.get(
        "CLAIM_STYLES",
        os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "styles")))

    try:
        ledger = load_ledger(args.ledger)
    except (OSError, ValueError) as e:
        print("cannot load ledger: %s" % e, file=sys.stderr)
        return 2

    findings = []
    claims = check_schema(ledger or {}, findings)
    check_retired(ledger or {}, claims, findings)
    if claims:
        check_run_records_schema(claims, findings)
        check_tool_outputs_schema(claims, findings)
        check_sanitizer_runs_schema(claims, findings)
        check_static_analysis_runs_schema(claims, findings)
        run_log_root = args.run_log_root or root
        tool_output_root = args.tool_output_root or root
        check_evidence(claims, root, args.max_age_days, findings, run_log_root,
                       tool_output_root)
        report_ids, def_names = build_suite_index(root, args.suite_glob)
        check_traceability(claims, report_ids, def_names, findings)
        check_consistency(claims, report_ids, def_names, findings)
        check_relevance(claims, findings)
    if os.path.isdir(root):
        if args.no_vale:
            check_prose_internal(root, args.docs_glob, findings)
        else:
            check_prose(root, args.docs_glob, styles_path, findings)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    print("ledger: %s | claims: %d" % (args.ledger, len(claims)))
    for check in ("L1", "L2", "L3", "L4", "L5", "L6"):
        rows = [f for f in findings if f.check == check]
        label = {"L1": "schema", "L2": "evidence", "L3": "traceability",
                 "L4": "consistency", "L5": "prose", "L6": "relevance"}[check]
        if not rows:
            print("  %s %-13s OK" % (check, label))
        else:
            print("  %s %-13s %d error(s), %d warning(s), %d info"
                  % (check, label,
                     sum(1 for f in rows if f.severity == "error"),
                     sum(1 for f in rows if f.severity == "warning"),
                     sum(1 for f in rows if f.severity == "info")))
            for f in rows:
                if f.severity != "info":
                    print("      %s" % f.render())
    print("total: %d error(s), %d warning(s), %d info" % (len(errors), len(warnings), len(infos)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
