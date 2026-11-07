#!/usr/bin/env python3
"""Claim ledger linter — the executable subset of the evidence-first contract.

Implements phase-1 checks over a claim ledger (JSON or YAML, see
schemas/claim-ledger.schema.json):

  L1  schema:        required fields, stable IDs, unique IDs, status and
                     evidence-kind enums, kind=test requires tests,
                     status=open requires limitations, run_record shape
  L2  evidence:      artifact paths exist, commits resolvable, dates within
                     the freshness window, run_record log and artifact hashes
                     match, the run exited 0 for a non-open claim, every cited
                     test appears in the captured log with a status
  L3  traceability:  every test ID in kind=test evidence exists in the suite
  L4  consistency:   status matches the strongest evidence channel; stronger
                     evidence than the status is a warning
  L5  prose:         unqualified absolutes in .md documents. Engine order:
                     Vale (if installed; styles/RussianAbsolutes package),
                     fallback to the built-in line scanner.

A run_record (schemas/run-record.schema.json) is optional: a kind=test record
without one gets an L2 warning, because re-dating and citing a test that never
ran stay invisible. With one, L2 hashes the log and the artifact and checks
that the cited test IDs appear in the log. This detects re-dating and edited
logs only if the forger does not also rewrite the record; without an external
anchor (C-13) a consistent forgery passes.

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 tool/usage error.

Usage:
    python3 tools/claim_lint.py [--root PATH] [--suite-glob GLOB]
                                [--max-age-days N] [--docs-glob GLOB]
                                [--run-log-root PATH] [--no-vale]
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
    return [c for c in claims if isinstance(c, dict)]


# ------------------------------------------------ run records (V2-01/V2-02)

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


def check_evidence(claims, root, max_age_days, findings, run_log_root=None):
    run_log_root = run_log_root or root
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
            commit = ev.get("commit")
            if commit:
                r = subprocess.run(
                    ["git", "cat-file", "-e", "%s^{commit}" % commit],
                    cwd=root, capture_output=True)
                if r.returncode != 0:
                    findings.append(Finding("L2", "error", "commit not resolvable: %s" % commit, c["id"]))
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
    if claims:
        check_run_records_schema(claims, findings)
        run_log_root = args.run_log_root or root
        check_evidence(claims, root, args.max_age_days, findings, run_log_root)
        report_ids, def_names = build_suite_index(root, args.suite_glob)
        check_traceability(claims, report_ids, def_names, findings)
        check_consistency(claims, report_ids, def_names, findings)
    if os.path.isdir(root):
        if args.no_vale:
            check_prose_internal(root, args.docs_glob, findings)
        else:
            check_prose(root, args.docs_glob, styles_path, findings)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    print("ledger: %s | claims: %d" % (args.ledger, len(claims)))
    for check in ("L1", "L2", "L3", "L4", "L5"):
        rows = [f for f in findings if f.check == check]
        label = {"L1": "schema", "L2": "evidence", "L3": "traceability",
                 "L4": "consistency", "L5": "prose"}[check]
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
