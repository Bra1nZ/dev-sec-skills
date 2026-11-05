#!/usr/bin/env python3
"""Claim ledger linter — the executable subset of the evidence-first contract.

Implements phase-1 checks over a claim ledger (JSON or YAML, see
schemas/claim-ledger.schema.json):

  L1  schema:        required fields, stable IDs, unique IDs, status and
                     evidence-kind enums, kind=test requires tests,
                     status=open requires limitations
  L2  evidence:      artifact paths exist, commits resolvable, dates within
                     the freshness window
  L3  traceability:  every test ID in kind=test evidence exists in the suite
  L4  consistency:   status matches the strongest evidence channel; stronger
                     evidence than the status is a warning
  L5  prose:         unqualified absolutes in .md documents. Engine order:
                     Vale (if installed; styles/RussianAbsolutes package),
                     fallback to the built-in line scanner.

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 tool/usage error.

Usage:
    python3 tools/claim_lint.py [--root PATH] [--suite-glob GLOB]
                                [--max-age-days N] [--docs-glob GLOB]
                                [--no-vale] ledger.json|yaml
"""

import argparse
import fnmatch
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


# ------------------------------------------------------- L2 evidence health

def check_evidence(claims, root, max_age_days, findings):
    today = date.today()
    for c in claims:
        for ev in c.get("evidence") or []:
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
    ap.add_argument("--no-vale", action="store_true",
                    help="skip Vale and use the built-in L5 scanner")
    args = ap.parse_args()

    root = args.root or os.path.dirname(os.path.abspath(args.ledger))
    if not os.path.isfile(args.ledger):
        print("ledger not found: %s" % args.ledger, file=sys.stderr)
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
        check_evidence(claims, root, args.max_age_days, findings)
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
