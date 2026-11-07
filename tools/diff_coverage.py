#!/usr/bin/env python3
"""Diff coverage — every changed declared choke point must map to a claim.

V2-07. Reads a cell registry, a claim ledger and a git range, and checks the
choke points the registry declares through `enforced_at`:

  DC1 path:    a declared choke-point path changed in the diff and no
               non-open claim maps it
  DC2 symbol:  a symbol declared in `enforced_at` changed and no non-open
               claim maps it
  DC3 decl:    an `enforced_at` value cannot be located in the repository
               (no leading path, the path is absent at base and head, or the
               path escapes the repository root)
  DC4 empty:   no declared choke point changed in the range — the gate is
               vacuous, and says so
  DC5 empty:   the registry declares no `enforced_at` at all

A choke point maps to a claim when one of these holds:

  * a cell that declares it carries a `claim_ids` entry that resolves to a
    non-open claim in the ledger;
  * a non-open claim's evidence `artifact` is the declared path;
  * a non-open claim's evidence `tests` (or a `negative_test`) cites the
    declared symbol.

An `open` claim does not count: an open claim is a plan, not coverage.

Changed symbols are located structurally through `tools/choke_points.py`, not by
a line scanner. Python definitions use the standard-library `ast`, so a
decorator, a body-only edit and a `def` inside a docstring are all handled
exactly. Rust `fn` spans come from a comment/string-aware lexer and brace
matching. SQL spans cover the whole `CREATE ... FUNCTION ...;` statement,
including a dollar-quoted body, so an edit that never repeats the function
name is still attributed. A symbol the parser cannot locate in a side of the
diff falls back to the token appearing on a changed line, with that file's
comments and literals blanked first, so a mention inside a comment is not a
change. Unknown extensions keep only the unmasked token fallback.

Exit codes: 0 no errors, 1 errors, 2 tool/usage error.

Usage:
    python3 tools/diff_coverage.py --repo ../target --base v1.3.1 \
        --head HEAD --cells spec/cells.yaml --ledger docs/claims.yaml \
        [--max-unmapped 0] [--json report.json]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

try:
    from choke_points import masked_lines_for, spans_for
except ImportError:  # vendored alone or imported from another directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from choke_points import masked_lines_for, spans_for

ENFORCED_PATH_RE = re.compile(r"^([A-Za-z0-9_./-]+):(\d+)\b")
FUNCTION_RE = re.compile(r"\bFUNCTION\s+([A-Za-z_][A-Za-z0-9_.]*)")
CALL_RE = re.compile(r"\(([A-Za-z_][A-Za-z0-9_.]*)")


class Finding(object):
    def __init__(self, check, severity, message):
        self.check = check
        self.severity = severity
        self.message = message

    def render(self):
        return "[%s] %-7s %s" % (self.check, self.severity, self.message)


class ChokePoint(object):
    def __init__(self, path, symbol=None):
        self.path = path
        self.symbol = symbol
        self.cells = []


def load(path):
    text = open(path, encoding="utf-8").read()
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("PyYAML is required for YAML files; pip install pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


def run_git(repo, args, check=True):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args),
                                                  proc.stderr.strip()[:300]))
    return proc


def resolve(repo, ref):
    proc = run_git(repo, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                   check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def blob(repo, sha, path):
    proc = run_git(repo, ["show", "%s:%s" % (sha, path)], check=False)
    return proc.stdout if proc.returncode == 0 else None


def exists_at(repo, sha, path):
    proc = run_git(repo, ["cat-file", "-t", "%s:%s" % (sha, path)], check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "blob"


def normalize(path):
    value = os.path.normpath(path).replace(os.sep, "/")
    if value.startswith("../") or value == ".." or os.path.isabs(path):
        return None
    return value


def name_status(repo, base, head, findings):
    """Return {changed_path: status}, including the old side of a rename."""
    out = run_git(repo, ["diff", "--name-status", "-z", "-M", base, head]).stdout
    parts = [p for p in out.split("\0") if p != ""]
    changed = {}
    index = 0
    while index < len(parts):
        status = parts[index]
        index += 1
        if status[:1] in ("R", "C"):
            if index + 1 >= len(parts):
                findings.append(Finding("DC3", "error",
                                        "cannot parse rename entry in git output"))
                break
            old, new = parts[index], parts[index + 1]
            index += 2
            changed[old] = status
            changed[new] = status
        else:
            if index >= len(parts):
                findings.append(Finding("DC3", "error",
                                        "cannot parse name-status entry in git output"))
                break
            changed[parts[index]] = status
            index += 1
    return changed


def diff_records(repo, base, head):
    """Return [{key, old_path, new_path, added, removed}] for every changed file.

    `added` and `removed` map line numbers to their text. The diff runs with
    --unified=0 and --no-prefix, so a hunk header is the only context and the
    paths are not ambiguous.
    """
    out = run_git(repo, ["-c", "core.quotePath=false", "diff", "--unified=0",
                         "--no-color", "--no-ext-diff", "--no-prefix", "-M",
                         base, head]).stdout
    records = []
    current = None
    old_no = new_no = 0

    def start(old_path, new_path):
        rec = {"key": new_path or old_path, "old_path": old_path,
               "new_path": new_path, "added": {}, "removed": {}}
        records.append(rec)
        return rec

    for line in out.splitlines():
        if line.startswith("--- "):
            value = line[4:]
            current = {"old_path": None if value == "/dev/null" else value,
                       "new_path": None, "added": {}, "removed": {}}
            continue
        if line.startswith("+++ "):
            value = line[4:]
            if current is not None:
                current["new_path"] = None if value == "/dev/null" else value
                current["key"] = current["new_path"] or current["old_path"]
                records.append(current)
            continue
        if line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                old_no, new_no = int(match.group(1)), int(match.group(2))
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current["added"][new_no] = line[1:]
            new_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            current["removed"][old_no] = line[1:]
            old_no += 1
        elif line.startswith(" "):
            old_no += 1
            new_no += 1
    return records


def record_for(records, path):
    for rec in records:
        if rec["key"] == path or rec["old_path"] == path or rec["new_path"] == path:
            return rec
    return None


def symbol_changed(repo, base, head, record, name):
    """True when a changed line touches a definition of `name`.

    Python and Rust produce structural spans from `choke_points`, and SQL
    produces a statement span that covers a `$$ ... $$` body, so an edit inside
    a body is attributed without the symbol name appearing on the line.

    The token fallback runs only when the parser finds no definition of `name`
    in that side of the diff. It looks at the file's own masked lines, not at
    the raw diff text, so a name inside a comment or a string cannot match.
    """
    pattern = re.compile(r"\b%s\b" % re.escape(name))
    sides = (
        (base, record["old_path"], record["removed"]),
        (head, record["new_path"], record["added"]),
    )
    for sha, side_path, touched in sides:
        if not side_path or not touched:
            continue
        text = blob(repo, sha, side_path)
        if text is None:
            continue
        target = side_path
        spans = spans_for(target, text, name)
        if spans:
            if any(first <= number <= last
                   for first, last in spans for number in touched):
                return True
            continue
        masked = masked_lines_for(target, text)
        for number in touched:
            if 0 < number <= len(masked) and pattern.search(masked[number - 1]):
                return True
    return False


def declarations(registry, repo, base, head, findings):
    paths = {}
    symbols = {}
    for cell in registry.get("cells") or []:
        value = cell.get("enforced_at")
        if not isinstance(value, str) or not value.strip():
            continue
        match = ENFORCED_PATH_RE.match(value.strip())
        path = normalize(match.group(1)) if match else None
        if path is None:
            findings.append(Finding("DC3", "error",
                                    "%s: enforced_at has no repository path: %r"
                                    % (cell.get("id"), value[:120])))
            continue
        if not (exists_at(repo, base, path) or exists_at(repo, head, path)):
            findings.append(Finding("DC3", "error",
                                    "%s: enforced_at path %r is absent at base and head"
                                    % (cell.get("id"), path)))
            continue
        point = paths.setdefault(path, ChokePoint(path))
        if cell not in point.cells:
            point.cells.append(cell)
        symbol = None
        function = FUNCTION_RE.search(value)
        if function:
            symbol = function.group(1)
        else:
            call = CALL_RE.search(value)
            if call:
                symbol = call.group(1)
        if symbol:
            entry = symbols.setdefault((path, symbol), ChokePoint(path, symbol))
            if cell not in entry.cells:
                entry.cells.append(cell)
    return paths, symbols


def claim_index(ledger):
    non_open = {}
    artifacts = {}
    tests = {}
    for claim in ledger.get("claims") or []:
        if claim.get("status") == "open":
            continue
        cid = claim.get("id")
        non_open[cid] = claim
        for evidence in claim.get("evidence") or []:
            artifact = evidence.get("artifact")
            if isinstance(artifact, str) and artifact.strip():
                normalized = normalize(artifact)
                if normalized:
                    artifacts.setdefault(normalized, set()).add(cid)
            for test_id in evidence.get("tests") or []:
                tests.setdefault(str(test_id), set()).add(cid)
    return non_open, artifacts, tests


def cells_claims(cell, non_open):
    return [cid for cid in cell.get("claim_ids") or [] if cid in non_open]


def path_claims(point, non_open, artifacts):
    mapped = set(artifacts.get(point.path, set()))
    for cell in point.cells:
        mapped.update(cells_claims(cell, non_open))
    return sorted(mapped)


def symbol_claims(point, non_open, tests):
    mapped = set(tests.get(point.symbol, set()))
    for cell in point.cells:
        mapped.update(cells_claims(cell, non_open))
    return sorted(mapped)


def main():
    ap = argparse.ArgumentParser(description="Diff coverage of declared choke points (V2-07)")
    ap.add_argument("--repo", required=True, help="git repository to inspect")
    ap.add_argument("--base", required=True, help="base ref of the diff")
    ap.add_argument("--head", default="HEAD", help="head ref of the diff (default HEAD)")
    ap.add_argument("--cells", required=True, help="cell registry with enforced_at")
    ap.add_argument("--ledger", required=True, help="claim ledger")
    ap.add_argument("--max-unmapped", type=int, default=0,
                    help="fail when more changed choke points are unmapped (default 0)")
    ap.add_argument("--json", default=None, help="write the summary as JSON")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        print("repo not found: %s" % args.repo, file=sys.stderr)
        return 2
    base_sha = resolve(repo, args.base)
    head_sha = resolve(repo, args.head)
    if base_sha is None or head_sha is None:
        print("not a git repository or ref does not resolve: %s / %s"
              % (args.base, args.head), file=sys.stderr)
        return 2
    try:
        registry = load(args.cells)
        ledger = load(args.ledger)
    except (OSError, ValueError) as e:
        print("cannot load input: %s" % e, file=sys.stderr)
        return 2
    if not isinstance(registry, dict) or not isinstance(registry.get("cells"), list):
        print("not a cell registry: %s" % args.cells, file=sys.stderr)
        return 2
    if not isinstance(ledger, dict) or not isinstance(ledger.get("claims"), list):
        print("not a claim ledger: %s" % args.ledger, file=sys.stderr)
        return 2

    findings = []
    try:
        changed = name_status(repo, base_sha, head_sha, findings)
        records = diff_records(repo, base_sha, head_sha)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2

    paths, symbols = declarations(registry, repo, base_sha, head_sha, findings)
    non_open, artifacts, tests = claim_index(ledger)

    changed_paths, changed_symbols = [], []
    for point in paths.values():
        if point.path in changed or record_for(records, point.path):
            claims = path_claims(point, non_open, artifacts)
            changed_paths.append({"id": point.path, "kind": "path",
                                  "claims": claims, "mapped": bool(claims)})
    for (point_path, symbol), point in symbols.items():
        record = record_for(records, point_path)
        if record is None:
            continue
        if symbol_changed(repo, base_sha, head_sha, record, symbol):
            claims = symbol_claims(point, non_open, tests)
            changed_symbols.append({"id": "%s::%s" % (point_path, symbol),
                                    "kind": "symbol", "path": point_path,
                                    "symbol": symbol, "claims": claims,
                                    "mapped": bool(claims)})

    entities = changed_paths + changed_symbols
    mapped = sum(1 for entity in entities if entity["mapped"])
    unmapped = [entity for entity in entities if not entity["mapped"]]
    share = (float(mapped) / len(entities)) if entities else None

    for entity in changed_paths:
        if not entity["mapped"]:
            findings.append(Finding("DC1", "info",
                                    "changed choke-point path %r maps to no non-open claim"
                                    % entity["id"]))
    for entity in changed_symbols:
        if not entity["mapped"]:
            findings.append(Finding("DC2", "info",
                                    "changed choke-point symbol %r maps to no non-open claim"
                                    % entity["id"]))
    if len(unmapped) > args.max_unmapped:
        for check, kind, label in (("DC1", "path", "paths"),
                                   ("DC2", "symbol", "symbols")):
            count = sum(1 for entity in unmapped if entity["kind"] == kind)
            if count:
                findings.append(Finding(check, "error",
                                        "%d unmapped changed choke-point %s "
                                        "(threshold --max-unmapped %d for all kinds, "
                                        "%d unmapped in total)"
                                        % (count, label, args.max_unmapped,
                                           len(unmapped))))
    if not paths and not symbols:
        findings.append(Finding("DC5", "info",
                                "the registry declares no enforced_at choke point"))
    elif not entities:
        findings.append(Finding("DC4", "info",
                                "no declared choke point changed in %s..%s"
                                % (args.base, args.head)))

    print("diff coverage: %s %s..%s (%s..%s)"
          % (args.repo, args.base, args.head, base_sha[:12], head_sha[:12]))
    print("  changed files: %d" % len(changed))
    print("  declared choke points: %d path(s), %d symbol(s)"
          % (len(paths), len(symbols)))
    print("  changed choke points: %d (mapped %d, unmapped %d)"
          % (len(entities), mapped, len(unmapped)))
    print("  mapped share: %s" % ("n/a" if share is None
                                  else "%.1f%%" % (share * 100)))
    for entity in entities:
        state = "mapped   " if entity["mapped"] else "UNMAPPED "
        print("    %s %s %s%s"
              % (state, entity["kind"], entity["id"],
                 "" if not entity["claims"] else " -> " + ", ".join(entity["claims"])))
    for check, label in (("DC1", "paths"), ("DC2", "symbols"),
                         ("DC3", "declarations"), ("DC4", "empty diff"),
                         ("DC5", "empty registry")):
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
        payload = {
            "repo": args.repo, "base": args.base, "base_sha": base_sha,
            "head": args.head, "head_sha": head_sha,
            "measured": date.today().isoformat(),
            "changed_files": sorted(changed),
            "declared": {"paths": sorted(paths), "symbols": len(symbols)},
            "changed": {"paths": changed_paths, "symbols": changed_symbols,
                        "mapped": mapped, "unmapped": len(unmapped),
                        "share": share},
            "findings": [{"check": f.check, "severity": f.severity,
                          "message": f.message} for f in findings],
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
