#!/usr/bin/env python3
"""Structural choke-point extractor and cell-class mapper (V2-22).

A *choke point* is a place where an invariant is enforced. The registry records
the ones a human declared in `enforced_at`; this tool finds *candidates* by
scanning ordinary code and maps each candidate to the taxonomy classes of
`cell-registry.schema.json`.

Extraction is structural, not textual:

  * Python uses the standard-library `ast`, so comments, strings, decorators and
    line ranges are exact; a `def` inside a docstring is not a definition.
  * Rust uses a lexer for line/block comments, strings, raw strings and char
    literals, then matches `fn` braces. It is not a full Rust parser: macros,
    generated code and unusual const-generic braces are outside its grammar.
  * SQL uses a lexer for comments, quoted strings, quoted identifiers and
    dollar-quoted bodies, then splits statements on top-level semicolons. A
    `CREATE FUNCTION ... AS $$ ... $$` span covers the whole body, so a
    body-only edit is visible.
  * Any other extension is skipped and counted; it is not guessed.

Candidate selection and class mapping are configuration, not code:
`spec/choke-points/rules.yaml` defines *signals* (why a definition is a
candidate) and *rules* (which cell classes it maps to). Rules are ordered; the
first match wins. A candidate that matches no rule is reported as
`unclassified` instead of being forced into `other`: `other` is a cell escape
hatch that requires a `routing_note`, while an unclassified scan result is a
gap in the rule file.

The output is a review queue. A class match is a reason to look at a site, not
evidence that the site enforces the invariant, and not a cell.

Exit codes: 0 no errors, 1 a threshold was exceeded, 2 tool or input error.

Usage:
    python3 tools/choke_points.py --root ../target \
        --rules spec/choke-points/rules.yaml \
        [--schema spec/conveyor/cell-registry.schema.json] \
        [--glob '*.py' ...] [--max-unclassified N] [--json report.json]
"""

import argparse
import ast
import fnmatch
import io
import json
import os
import re
import sys
import tokenize
from datetime import date

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

LANGUAGES = {".py": "python", ".rs": "rust", ".sql": "sql"}
DEFAULT_GLOBS = ("*.py", "*.rs", "*.sql")
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache",
}
TAXONOMY_DEFAULT = {"security", "correctness", "maintainability",
                    "performance", "other"}
FAILURE_MODE_DEFAULT = {"deny", "abort", "rollback", "safe-degrade", "detect",
                        "other"}
FIELDS = {"name", "calls", "decorators", "path", "kind"}


class Definition(object):
    def __init__(self, path, name, qualname, language, kind, start, end,
                 decorators=None, calls=None):
        self.path = path
        self.name = name
        self.qualname = qualname
        self.language = language
        self.kind = kind
        self.start = start
        self.end = end
        self.decorators = list(decorators or [])
        self.calls = list(calls or [])

    def field(self, name):
        if name == "name":
            return self.qualname
        if name == "calls":
            return " ".join(self.calls)
        if name == "decorators":
            return " ".join(self.decorators)
        if name == "path":
            return self.path
        if name == "kind":
            return self.kind
        return ""

    def as_dict(self):
        return {
            "path": self.path,
            "symbol": self.name,
            "qualname": self.qualname,
            "language": self.language,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "decorators": self.decorators,
            "calls": self.calls,
        }


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def _blank(chars, start, end):
    for index in range(start, min(end, len(chars))):
        if chars[index] not in "\r\n":
            chars[index] = " "


def _offsets(text):
    lines = text.splitlines(True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return starts


def _mask_python(text):
    """Blank comments and string tokens; keep newlines and offsets."""
    starts = _offsets(text)
    chars = list(text)

    def offset(position):
        line, col = position
        if line - 1 >= len(starts):
            return len(text)
        return starts[line - 1] + col

    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                _blank(chars, offset(token.start), offset(token.end))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    return "".join(chars)


def _rust_raw_end(text, index):
    """Return the end offset of a Rust raw/byte string starting at index."""
    cursor = index
    if text.startswith("br", cursor) or text.startswith("rb", cursor):
        cursor += 2
    elif text.startswith("r", cursor):
        cursor += 1
    else:
        return None
    hashes = 0
    while cursor < len(text) and text[cursor] == "#":
        hashes += 1
        cursor += 1
    if cursor >= len(text) or text[cursor] != '"':
        return None
    cursor += 1
    closing = '"' + "#" * hashes
    end = text.find(closing, cursor)
    return len(text) if end < 0 else end + len(closing)


def _rust_string_end(text, index, prefix=1):
    cursor = index + prefix
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == '"':
            return cursor + 1
        cursor += 1
    return len(text)


def _rust_mask(text):
    chars = list(text)
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end < 0 else end
            _blank(chars, index, end)
            index = end
            continue
        if text.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if text.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif text.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            _blank(chars, index, cursor)
            index = cursor
            continue
        char = text[index]
        if char == "r" or (char == "b" and text.startswith(("br", "b\""), index)):
            end = _rust_raw_end(text, index)
            if end is not None:
                _blank(chars, index, end)
                index = end
                continue
        if text.startswith('b"', index) or text.startswith('c"', index):
            end = _rust_string_end(text, index)
            _blank(chars, index, end)
            index = end
            continue
        if char == '"':
            end = _rust_string_end(text, index)
            _blank(chars, index, end)
            index = end
            continue
        if char == "'":
            match = re.match(
                r"'(?:\\u\{[0-9A-Fa-f]+\}|\\x[0-9A-Fa-f]{2}|\\.|[^\\'\n])'",
                text[index:])
            if match:
                end = index + match.end()
                _blank(chars, index, end)
                index = end
                continue
            # A lifetime such as `'a`, not a char literal.
            index += 1
            continue
        index += 1
    return "".join(chars)


def _sql_mask(text):
    """Blank SQL comments and literals; return (masked, literal_spans)."""
    chars = list(text)
    literals = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("--", index):
            end = text.find("\n", index)
            end = length if end < 0 else end
            _blank(chars, index, end)
            index = end
            continue
        if text.startswith("/*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth:
                if text.startswith("/*", cursor):
                    depth += 1
                    cursor += 2
                elif text.startswith("*/", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            _blank(chars, index, cursor)
            index = cursor
            continue
        char = text[index]
        if char == "'":
            escape = (index > 0 and text[index - 1] in "Ee"
                      and (index < 2 or not (text[index - 2].isalnum()
                                             or text[index - 2] == "_")))
            cursor = index + 1
            while cursor < length:
                if escape and text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == "'":
                    if cursor + 1 < length and text[cursor + 1] == "'":
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            literals.append((index, cursor))
            _blank(chars, index, cursor)
            index = cursor
            continue
        if char == '"':
            cursor = index + 1
            while cursor < length:
                if text[cursor] == '"':
                    if cursor + 1 < length and text[cursor + 1] == '"':
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            literals.append((index, cursor))
            _blank(chars, index, cursor)
            index = cursor
            continue
        if char == "$":
            match = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", text[index:])
            if match:
                tag = match.group(0)
                cursor = text.find(tag, index + len(tag))
                if cursor < 0:
                    cursor = length
                else:
                    cursor += len(tag)
                literals.append((index, cursor))
                _blank(chars, index, cursor)
                index = cursor
                continue
        index += 1
    return "".join(chars), literals


def _py_calls(node):
    calls = []

    def walk(current):
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name):
                    calls.append(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.append(func.attr)
            walk(child)

    walk(node)
    return calls


def _py_defs(path, text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as error:
        line = getattr(error, "lineno", "?")
        return [], "line %s: %s" % (line, getattr(error, "msg", str(error)))

    defs = []

    def decorator_name(node):
        try:
            return ast.unparse(node)
        except Exception:
            return node.__class__.__name__

    def walk(node, parents):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                parent_kind = parents[-1][1] if parents else None
                if isinstance(child, ast.ClassDef):
                    kind = "class"
                elif parent_kind == "class":
                    kind = "method"
                else:
                    kind = "function"
                names = [item[0] for item in parents] + [child.name]
                decorators = [decorator_name(item)
                              for item in child.decorator_list]
                calls = [] if kind == "class" else _py_calls(child)
                start = min([child.lineno] + [item.lineno
                                             for item in child.decorator_list])
                end = getattr(child, "end_lineno", None) or child.lineno
                defs.append(Definition(path, child.name, ".".join(names),
                                       "python", kind, start, end,
                                       decorators, calls))
                walk(child, parents + [(child.name, kind)])
            else:
                walk(child, parents)

    walk(tree, [])
    return defs, None


def _rust_match_brace(masked, start):
    depth = 0
    for cursor in range(start, len(masked)):
        if masked[cursor] == "{":
            depth += 1
        elif masked[cursor] == "}":
            depth -= 1
            if depth == 0:
                return cursor
    return len(masked) - 1


def _rust_attributes(text, start_line):
    lines = text.splitlines()
    attributes = []
    first = start_line
    index = start_line - 2
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            break
        if not stripped.startswith("#"):
            break
        attributes.append(stripped)
        first = index + 1
        index -= 1
    attributes.reverse()
    return first, attributes


def _rust_defs(path, text):
    masked = _rust_mask(text)
    defs = []
    for match in re.finditer(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", masked):
        name = match.group(1)
        cursor = match.end()
        depth = 0
        body = None
        terminator = None
        while cursor < len(masked):
            char = masked[cursor]
            if char in "([":
                depth += 1
            elif char in ")]":
                depth = max(0, depth - 1)
            elif char == "{" and depth == 0:
                body = cursor
                break
            elif char == ";" and depth == 0:
                terminator = cursor
                break
            cursor += 1
        if body is None and terminator is None:
            end_offset = len(masked) - 1
        elif body is not None:
            end_offset = _rust_match_brace(masked, body)
        else:
            end_offset = terminator
        start_line = line_of(text, match.start())
        start_line, attributes = _rust_attributes(text, start_line)
        calls = []
        if body is not None:
            body_text = masked[body:end_offset + 1]
            for call in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_:]*)\s*\(", body_text):
                candidate = call.group(1)
                if candidate not in {
                        "if", "while", "for", "match", "fn", "return", "let",
                        "move", "async", "await", "Some", "Ok", "Err"}:
                    calls.append(candidate)
        defs.append(Definition(path, name, name, "rust", "function",
                               start_line, line_of(text, end_offset),
                               attributes, calls))
    return defs, None


def _sql_statements(masked):
    statements = []
    start = 0
    for index, char in enumerate(masked):
        if char == ";":
            statements.append((start, index + 1))
            start = index + 1
    if masked[start:].strip():
        statements.append((start, len(masked)))
    return statements


SQL_KEYWORDS = {
    "if", "and", "or", "not", "select", "from", "where", "values", "on",
    "in", "exists", "case", "when", "then", "else", "end", "as", "language",
    "returns", "returning", "table", "function", "procedure", "create",
    "replace", "begin", "declare", "raise", "perform", "return", "loop",
    "for", "while", "coalesce", "nullif", "cast", "array", "row", "with",
    "insert", "update", "delete", "into", "set", "using", "grant", "revoke",
}


def _sql_calls(text):
    calls = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_.]*)\s*\(", text):
        name = match.group(1)
        if name.lower() not in SQL_KEYWORDS:
            calls.append(name)
    return calls


def _sql_defs(path, text):
    masked, _ = _sql_mask(text)
    defs = []
    for start, end in _sql_statements(masked):
        statement = masked[start:end]
        stripped = statement.lstrip()
        offset = start + len(statement) - len(stripped)
        patterns = (
            (r"^CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z_][A-Za-z0-9_.$]*)",
             "sql-function"),
            (r"^CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([A-Za-z_][A-Za-z0-9_.$]*)",
             "sql-procedure"),
            (r"^CREATE\s+(?:OR\s+REPLACE\s+)?POLICY\s+([A-Za-z_][A-Za-z0-9_.$]*)",
             "sql-policy"),
            (r"^CREATE\s+(?:CONSTRAINT\s+)?TRIGGER\s+([A-Za-z_][A-Za-z0-9_.$]*)",
             "sql-trigger"),
            (r"^CREATE\s+ROLE\s+([A-Za-z_][A-Za-z0-9_.$]*)", "sql-role"),
            (r"^DROP\s+FUNCTION\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_.$]*)",
             "sql-function"),
            (r"^ALTER\s+FUNCTION\s+([A-Za-z_][A-Za-z0-9_.$]*)", "sql-function"),
            (r"^ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_.$]*).*"
             r"ENABLE\s+ROW\s+LEVEL\s+SECURITY", "sql-rls"),
        )
        for pattern, kind in patterns:
            match = re.match(pattern, stripped, re.I)
            if not match:
                continue
            name = match.group(1)
            defs.append(Definition(path, name, name, "sql", kind,
                                   line_of(text, offset),
                                   line_of(text, end - 1),
                                   [], _sql_calls(masked[start:end])))
            break
    return defs, None


def extract_file(path, text):
    """Return (definitions, parse_error) for one file."""
    extension = os.path.splitext(path)[1].lower()
    if extension == ".py":
        return _py_defs(path, text)
    if extension == ".rs":
        return _rust_defs(path, text)
    if extension == ".sql":
        return _sql_defs(path, text)
    return [], None


def language_for(path):
    return LANGUAGES.get(os.path.splitext(path)[1].lower())


def spans_for(path, text, name):
    """Line spans of definitions named `name`; empty when the parser finds none."""
    definitions, _ = extract_file(path, text)
    spans = set()
    for definition in definitions:
        names = {definition.name, definition.qualname}
        if (name in names or definition.qualname.endswith("." + name)
                or definition.qualname.endswith("::" + name)):
            spans.add((definition.start, definition.end))
    return sorted(spans)


def masked_lines_for(path, text):
    """Lines with comments and literals blanked, for the last-resort fallback."""
    extension = os.path.splitext(path)[1].lower()
    if extension == ".py":
        masked = _mask_python(text)
    elif extension == ".rs":
        masked = _rust_mask(text)
    elif extension == ".sql":
        masked, _ = _sql_mask(text)
    else:
        masked = text
    return masked.splitlines()


def load_config(path):
    text = open(path, encoding="utf-8").read()
    if yaml is None:
        raise ValueError("PyYAML is required; pip install pyyaml")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("rules file must be a mapping")
    signals = data.get("signals") or []
    rules = data.get("rules") or []
    if not isinstance(signals, list) or not isinstance(rules, list):
        raise ValueError("signals and rules must be lists")
    seen = set()
    for signal in signals:
        if not isinstance(signal, dict) or not signal.get("id"):
            raise ValueError("each signal needs an id")
        if signal["id"] in seen:
            raise ValueError("duplicate signal id %r" % signal["id"])
        seen.add(signal["id"])
        fields = signal.get("fields") or []
        if not fields or not set(fields) <= FIELDS:
            raise ValueError("signal %r has invalid fields" % signal["id"])
        _compile(signal.get("pattern"), "signal %r" % signal["id"])
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("id"):
            raise ValueError("each rule needs an id")
        if rule["id"] in seen:
            raise ValueError("duplicate rule id %r" % rule["id"])
        seen.add(rule["id"])
        if not rule.get("taxonomy_class"):
            raise ValueError("rule %r has no taxonomy_class" % rule["id"])
        if rule["taxonomy_class"] == "other":
            raise ValueError("rule %r maps to 'other'; use an unclassified "
                             "candidate instead" % rule["id"])
        if rule.get("failure_mode") == "other":
            raise ValueError("rule %r maps to failure_mode 'other'; use an "
                             "unclassified candidate instead" % rule["id"])
        match = rule.get("match") or {}
        if not isinstance(match, dict) or not match:
            raise ValueError("rule %r has an empty match" % rule["id"])
        if not set(match) <= FIELDS:
            raise ValueError("rule %r has invalid match fields" % rule["id"])
        for field, pattern in match.items():
            _compile(pattern, "rule %r field %r" % (rule["id"], field))
    return {"signals": signals, "rules": rules}


def _compile(pattern, label):
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("%s has no pattern" % label)
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError("%s has an invalid regex: %s" % (label, error))


def schema_enums(path):
    data = json.load(open(path, encoding="utf-8"))
    try:
        cell = data["definitions"]["cell"]["properties"]
        taxonomy = set(cell["taxonomy_class"]["enum"])
        failure_mode = set(cell["failure_mode"]["enum"])
    except (KeyError, TypeError):
        raise ValueError("cannot read taxonomy enums from %s" % path)
    return taxonomy, failure_mode


def validate_rules(config, taxonomy, failure_modes):
    for rule in config["rules"]:
        if rule["taxonomy_class"] not in taxonomy:
            raise ValueError("rule %r has unknown taxonomy_class %r"
                             % (rule["id"], rule["taxonomy_class"]))
        if rule.get("failure_mode") not in failure_modes:
            raise ValueError("rule %r has unknown failure_mode %r"
                             % (rule["id"], rule.get("failure_mode")))
        if not rule.get("failure_class"):
            raise ValueError("rule %r has no failure_class" % rule["id"])


def signals_for(definition, signals):
    matched = []
    for signal in signals:
        for field in signal["fields"]:
            value = definition.field(field)
            if value and re.search(signal["pattern"], value):
                matched.append(signal["id"])
                break
    return matched


def classify(definition, rules):
    for rule in rules:
        for field, pattern in rule["match"].items():
            value = definition.field(field)
            if value:
                match = re.search(pattern, value)
                if match:
                    return rule, field, match.group(0)[:120]
    return None, None, None


def iter_files(root, globs):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames
                             if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            if any(fnmatch.fnmatch(relative, pattern) for pattern in globs):
                yield full, relative


def scan(root, config, globs):
    definitions = []
    candidates = []
    files = {"scanned": 0, "skipped": 0, "by_language": {},
             "parse_errors": []}
    for full, relative in iter_files(root, globs):
        language = language_for(relative)
        if language is None:
            files["skipped"] += 1
            continue
        files["scanned"] += 1
        files["by_language"][language] = files["by_language"].get(language, 0) + 1
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError as error:
            files["parse_errors"].append({"path": relative, "error": str(error)})
            continue
        found, error = extract_file(relative, text)
        if error:
            files["parse_errors"].append({"path": relative, "error": error})
        definitions.extend(found)
        for definition in found:
            signals = signals_for(definition, config["signals"])
            if not signals:
                continue
            rule, field, evidence = classify(definition, config["rules"])
            payload = definition.as_dict()
            payload.update({
                "signals": signals,
                "taxonomy_class": rule["taxonomy_class"] if rule else None,
                "failure_class": rule["failure_class"] if rule else None,
                "failure_mode": rule["failure_mode"] if rule else None,
                "rule": rule["id"] if rule else None,
                "matched_field": field,
                "evidence": evidence,
            })
            candidates.append(payload)
    return definitions, candidates, files


def summarise(definitions, candidates, files):
    by_class = {}
    by_signal = {}
    by_language = {}
    unclassified = 0
    for candidate in candidates:
        if candidate["taxonomy_class"]:
            by_class[candidate["taxonomy_class"]] = (
                by_class.get(candidate["taxonomy_class"], 0) + 1)
        else:
            unclassified += 1
        for signal in candidate["signals"]:
            by_signal[signal] = by_signal.get(signal, 0) + 1
        by_language[candidate["language"]] = (
            by_language.get(candidate["language"], 0) + 1)
    return {
        "definitions": len(definitions),
        "candidates": len(candidates),
        "classified": len(candidates) - unclassified,
        "unclassified": unclassified,
        "by_class": by_class,
        "by_signal": by_signal,
        "by_language": by_language,
        "files": files,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Extract choke-point candidates and map them to cell classes (V2-22)")
    ap.add_argument("--root", required=True, help="repository or directory to scan")
    ap.add_argument("--rules", required=True, help="signals and class-mapping rules")
    ap.add_argument("--schema", default=None,
                    help="cell-registry schema; validates taxonomy and failure modes")
    ap.add_argument("--glob", action="append", default=None,
                    help="file glob (repeatable; default: *.py, *.rs, *.sql)")
    ap.add_argument("--max-unclassified", type=int, default=None,
                    help="fail when more candidates have no class rule")
    ap.add_argument("--max-parse-errors", type=int, default=None,
                    help="fail when more files cannot be parsed")
    ap.add_argument("--list", action="store_true",
                    help="print every candidate, not only the unclassified sample")
    ap.add_argument("--json", default=None, help="write the full scan as JSON")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("root not found: %s" % args.root, file=sys.stderr)
        return 2
    if not os.path.isfile(args.rules):
        print("rules not found: %s" % args.rules, file=sys.stderr)
        return 2
    try:
        config = load_config(args.rules)
        taxonomy, failure_modes = TAXONOMY_DEFAULT, FAILURE_MODE_DEFAULT
        if args.schema:
            taxonomy, failure_modes = schema_enums(args.schema)
        validate_rules(config, taxonomy, failure_modes)
        globs = tuple(args.glob) if args.glob else DEFAULT_GLOBS
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("cannot load rules: %s" % error, file=sys.stderr)
        return 2

    definitions, candidates, files = scan(root, config, globs)
    summary = summarise(definitions, candidates, files)

    print("choke points: %s" % args.root)
    print("  rules: %s" % args.rules)
    print("  files: %d scanned (%s), %d skipped"
          % (files["scanned"],
             ", ".join("%s %d" % (key, value)
                       for key, value in sorted(files["by_language"].items()))
             or "none",
             files["skipped"]))
    print("  definitions: %d" % summary["definitions"])
    print("  candidates: %d" % summary["candidates"])
    print("  classified: %d" % summary["classified"])
    print("  unclassified: %d" % summary["unclassified"])
    if summary["by_class"]:
        print("  by class: %s"
              % ", ".join("%s %d" % (key, value)
                          for key, value in sorted(summary["by_class"].items())))
    if files["parse_errors"]:
        print("  parse errors: %d" % len(files["parse_errors"]))
        for row in files["parse_errors"][:10]:
            print("    %s: %s" % (row["path"], row["error"]))
    if summary["unclassified"]:
        print("  unclassified candidates (first 20):")
        shown = 0
        for candidate in candidates:
            if candidate["taxonomy_class"] is not None:
                continue
            print("    %s::%s (%s %d-%d) signals=%s"
                  % (candidate["path"], candidate["qualname"],
                     candidate["kind"], candidate["start"], candidate["end"],
                     ",".join(candidate["signals"])))
            shown += 1
            if shown >= 20:
                break
    if args.list:
        print("  candidates:")
        for candidate in candidates:
            print("    %s::%s [%s] %s->%s rule=%s"
                  % (candidate["path"], candidate["qualname"],
                     ",".join(candidate["signals"]),
                     candidate["taxonomy_class"],
                     candidate["failure_mode"], candidate["rule"]))

    errors = 0
    if args.max_unclassified is not None:
        if summary["unclassified"] > args.max_unclassified:
            print("[CP1] error   %d unclassified candidates exceed "
                  "--max-unclassified %d"
                  % (summary["unclassified"], args.max_unclassified))
            errors += 1
    if args.max_parse_errors is not None:
        if len(files["parse_errors"]) > args.max_parse_errors:
            print("[CP2] error   %d parse errors exceed --max-parse-errors %d"
                  % (len(files["parse_errors"]), args.max_parse_errors))
            errors += 1
    print("total: %d error(s)" % errors)

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        os.makedirs(parent, exist_ok=True)
        payload = {
            "root": args.root,
            "measured": date.today().isoformat(),
            "rules": args.rules,
            "schema": args.schema,
            "globs": list(globs),
            "summary": summary,
            "candidates": candidates,
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
