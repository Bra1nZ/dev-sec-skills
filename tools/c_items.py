#!/usr/bin/env python3
"""Structural items in a C file: structs, unions, enums, functions.

Built on :mod:`rust_lexer`. The C subset of the token grammar is identical to
Rust's for the shapes the conveyor needs (identifiers, numbers, strings, char
literals, punctuation, comments), so the lexer is reused as is and only the
parser is C-specific. The parser understands the file-scope shapes the
conveyor needs and refuses to guess about anything else: a construct it
cannot delimit is reported back as ``unsupported`` instead of producing a
half-item.

What is recognised:

* ``struct``/``union`` with named fields and ``enum`` with variants
  (a union is reported as a struct: the consumers model fields, not tags);
* function definitions: ``return-type name(params) { body }``;
* ``static`` marks the operation private, everything else public;
* a non-const pointer first parameter makes the operation mut_self, with
  the parameter type as its receiver (a C function mutates through a
  pointer the way a Rust method mutates through ``&mut self``).

What is not recognised, and is either skipped or reported as
``unsupported``: preprocessor directives (``#include``, ``#define`` bodies
are excluded from scanning entirely, including line continuations), K&R
definitions, function pointers declared at file scope.
"""

from __future__ import annotations

from rust_lexer import IDENT, PUNCT, lex

# Tokens that begin a preprocessor directive (only used if pp skipping
# somehow misses a directive; the line-based set is authoritative).
_PP = "#"
# C keywords that can never introduce a function definition (return-type
# keywords included: in `unsigned long (*fp)(void)` the `long` sits right
# before the parameter-list parenthesis of a function-pointer typedef).
_NON_FN = {
    "if", "for", "while", "switch", "return", "sizeof", "case", "do",
    "else", "goto", "typedef", "extern", "struct", "union", "enum",
    "defined", "define", "include", "ifdef", "ifndef", "endif", "elif",
    "undef", "pragma", "line", "unsigned", "signed", "long", "short",
    "int", "char", "float", "double", "void", "const", "volatile",
    "register", "restrict", "inline", "_Bool", "_Atomic",
}


def _pp_lines(lines):
    """1-based line numbers belonging to preprocessor directives,
    honouring backslash continuations. Computed from the original source
    (before continuation stripping removes the very backslashes the
    detection needs)."""
    skip = set()
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].lstrip().startswith("#"):
            j = i
            while j < n and lines[j].rstrip().endswith("\\"):
                j += 1
            for k in range(i, min(j + 1, n)):
                skip.add(k + 1)
            i = j + 1
        else:
            i += 1
    return skip


def _is_ident(tok) -> bool:
    return tok.kind == IDENT


class CParser:
    """Parses one lexed C file into conveyor items."""

    def __init__(self, lexed, pp_lines):
        self.lexed = lexed
        self.t = lexed.tokens
        self.pairs = lexed.pairs
        self.unsupported = []
        self._pp = self._pp_tokens(pp_lines)

    # -- preprocessor ranges ----------------------------------------------

    def _pp_tokens(self, pp_lines):
        """Token indices inside preprocessor directives (they are excluded
        from scanning: a macro body with braces would corrupt the depth
        accounting at file scope)."""
        return set(i for i, tok in enumerate(self.t)
                   if tok.line in pp_lines)

    def _next(self, i, end):
        """Next token index after i that is not part of a directive."""
        i += 1
        while i < end and i in self._pp:
            i += 1
        return i

    # -- helpers -----------------------------------------------------------

    def _text(self, a, b):
        """Source text covered by tokens a..b inclusive."""
        if a > b:
            return ""
        return self.lexed.text_between(a, b)

    def _decl_start(self, i):
        """Start of the declaration that token i belongs to: scan back to
        the previous ``;``/``}``/``{`` or directive."""
        k = i - 1
        while k >= 0:
            if k in self._pp:
                break
            tok = self.t[k]
            if tok.kind == PUNCT and tok.text in (";", "}", "{"):
                break
            k -= 1
        return k + 1

    def _split(self, a, b, depth, sep):
        """Split tokens a..b inclusive on ``sep`` at nesting depth
        ``depth`` (0 = the level right inside a brace group)."""
        parts, cur, lvl = [], [], 0
        for i in range(a, b + 1):
            if i in self._pp:
                continue
            tok = self.t[i]
            if tok.kind == PUNCT:
                if tok.text in "{([":
                    lvl += 1
                elif tok.text in "})]":
                    lvl -= 1
                elif tok.text == sep and lvl == depth:
                    parts.append(cur)
                    cur = []
                    continue
            cur.append(i)
        if cur:
            parts.append(cur)
        return parts

    def _item(self, kind, name, visibility, start_idx, end_line):
        return {
            "kind": kind,
            "name": name,
            "owner": None,
            "visibility": visibility,
            "docs": [],
            "start_line": self.t[start_idx].line,
            "end_line": end_line,
        }

    # -- type items ---------------------------------------------------------

    def _type_item(self, i, kind_word):
        """Parse a struct/union/enum definition starting at token i.
        Returns (item, next_index) or (None, next_index) for declarations
        without a body."""
        tag = None
        j = self._next(i, len(self.t))
        if j < len(self.t) and _is_ident(self.t[j]):
            tag = self.t[j].text
            j = self._next(j, len(self.t))
        if j >= len(self.t) or self.t[j].text != "{":
            # forward declaration or variable of that type: skip to ';'
            k = j
            while k < len(self.t) and self.t[k].text != ";":
                k = self._next(k, len(self.t))
            return None, k + 1
        close = self.pairs[j]
        line = self.t[i].line
        name = tag
        if name is None:
            # typedef struct { ... } name;  — the name follows the body
            k = self._next(close, len(self.t))
            while k < len(self.t) and self.t[k].text != ";" and self.t[k].text != ",":
                if _is_ident(self.t[k]):
                    name = self.t[k].text
                    break
                k = self._next(k, len(self.t))
        if name is None:
            name = "anon-%s-%d" % (kind_word, line)
        item = self._item("struct" if kind_word in ("struct", "union")
                          else "enum", name, "public", i, self.t[close].line)
        if kind_word == "enum":
            item["form"] = "enum"
            item["variants"] = self._enum_variants(j + 1, close - 1)
        else:
            item["form"] = "named"
            item["fields"] = self._fields(j + 1, close - 1)
        return item, close + 1

    def _enum_variants(self, a, b):
        variants = []
        for part in self._split(a, b, 0, ","):
            if not part:
                continue
            first = part[0]
            if _is_ident(self.t[first]):
                variants.append({"name": self.t[first].text})
        return variants

    def _fields(self, a, b):
        """Fields of a struct/union body: ``type name;`` statements at
        depth 1. The name is the last identifier of the statement; the type
        is everything before it."""
        fields = []
        for part in self._split(a, b, 0, ";"):
            if not part:
                continue
            name_idx = None
            for pos, idx in enumerate(part):
                tok = self.t[idx]
                nxt = self.t[part[pos + 1]] if pos + 1 < len(part) else None
                if _is_ident(tok) and (nxt is None or nxt.text in (":", "[")
                                       or nxt.kind == PUNCT and nxt.text == ";"):
                    name_idx = pos
            if name_idx is None:
                self.unsupported.append({
                    "line": self.t[part[0]].line,
                    "reason": "field-without-name",
                    "detail": self._text(part[0], part[-1])[:80],
                })
                continue
            name_tok = part[name_idx]
            type_end = part[name_idx - 1] if name_idx > 0 else name_tok
            ftype = self._text(part[0], type_end).strip() or "int"
            # keep array suffix in the type, as Rust tuple forms keep arity
            if name_idx + 1 < len(part) and self.t[part[name_idx + 1]].text == "[":
                close = part[-1]
                if self.t[close].text == "]":
                    ftype += self._text(part[name_idx + 1], close)
            fields.append({
                "name": self.t[name_tok].text,
                "type": ftype,
                "visibility": "public",
                "line": self.t[part[0]].line,
                "end_line": self.t[part[-1]].line,
            })
        return fields

    # -- functions -----------------------------------------------------------

    def _fn(self, i, paren, end):
        """Parse a candidate function definition: name at token i, its
        parameter list opening at token ``paren``. Returns (item,
        next_index) or (None, next_index) for prototypes and
        non-definitions."""
        line = self.t[i].line
        close = self.pairs[paren]
        k = self._next(close, end)
        while k < end and self.t[k].kind == IDENT \
                and self.t[k].text in ("__attribute__", "__asm__", "asm"):
            # attribute/asm tail: skip its parenthesised group
            nxt = self._next(k, end)
            if nxt < end and self.t[nxt].text == "(":
                k = self._next(self.pairs[nxt], end)
            else:
                k = nxt
        if k >= end:
            return None, close + 1
        nxt = self.t[k]
        if nxt.text == ")":
            # nested declarator or call: `(*FN(name))(void)`, `if (f(x))` —
            # skip the enclosing parenthesised group without a complaint
            outer_open = self.pairs[k]
            outer_close = self.pairs.get(outer_open, k)
            return None, outer_close + 1
        if nxt.text == ";":
            return None, k + 1  # prototype
        if nxt.text == "=":
            # initialiser, not a function
            j = k
            while j < end and self.t[j].text != ";":
                j = self._next(j, end)
            return None, j + 1
        if nxt.text == "(":
            # function-pointer declarator: `type (*name)(params)` — skip
            # the parameter group, then expect ';' or an initialiser
            g2_close = self.pairs.get(k, k)
            k = self._next(g2_close, end)
            while k < end and self.t[k].text not in (";", "{", "="):
                k = self._next(k, end)
            if k >= end:
                return None, k
            if self.t[k].text == "{":
                pass  # fall through to the body path
            else:
                j = k
                while j < end and self.t[j].text != ";":
                    j = self._next(j, end)
                return None, j + 1
        elif nxt.text != "{":
            # macro invocation tail or K&R declaration list: skip silently
            # to ';' (a definition always reaches the '{' branch directly)
            j = k
            while j < end and self.t[j].text not in (";", "{"):
                j = self._next(j, end)
            if j < end and self.t[j].text == "{":
                self.unsupported.append({
                    "line": line, "reason": "fn-not-delimited",
                    "detail": self._text(i, min(i + 12, end - 1))[:80],
                })
                return None, self.pairs.get(j, j) + 1
            return None, j + 1
        body_open = k
        body_close = self.pairs[body_open]
        decl_start = self._decl_start(i)
        words = [self.t[x].text for x in range(decl_start, close + 1)]
        visibility = "private" if "static" in words else "public"
        params = self._split(paren + 1, close - 1, 0, ",")
        receiver = None
        mut_self = False
        for part in params:
            pwords = [self.t[idx].text for idx in part]
            if "*" in pwords and "const" not in pwords:
                name_positions = [x for x in part if _is_ident(self.t[x])]
                if name_positions:
                    recv_end = name_positions[-1] - 1 if name_positions[-1] > part[0] else part[-1]
                    receiver = self._text(part[0], recv_end).strip()
                    mut_self = True
                break
        signature = self._text(decl_start, body_open - 1).strip()
        item = self._item("fn", self.t[i].text, visibility, decl_start,
                          self.t[body_close].line)
        item["signature"] = signature
        item["params"] = [self._text(p[0], p[-1]) for p in params if p]
        item["receiver"] = receiver
        item["mut_self"] = mut_self
        item["body"] = (body_open + 1, body_close - 1)
        item["declaration_only"] = False
        return item, body_close + 1

    # -- main loop -----------------------------------------------------------

    def parse_items(self, start, end):
        items = []
        i = start
        while i < end:
            if i in self._pp:
                i = self._next(i, end)
                continue
            tok = self.t[i]
            if tok.kind == PUNCT and tok.text in ("{",) and (i == start or self._at_top(i, items)):
                # orphan brace group (global initialiser etc.): skip it
                close = self.pairs.get(i)
                i = (close + 1) if close is not None else i + 1
                continue
            if tok.kind == PUNCT and tok.text == "}":
                # unbalanced close at file scope: report and move on
                self.unsupported.append({
                    "line": tok.line, "reason": "unbalanced-brace",
                    "detail": "closing brace at file scope",
                })
                i += 1
                continue
            if tok.kind == IDENT and tok.text in ("struct", "union", "enum"):
                item, nxt = self._type_item(i, tok.text)
                if item:
                    items.append(item)
                i = nxt
                continue
            if tok.kind == IDENT and tok.text not in _NON_FN:
                nxt = self._next(i, end)
                if nxt < end and self.t[nxt].text == "(":
                    item, after = self._fn(i, nxt, end)
                    if item:
                        items.append(item)
                    i = after
                    continue
            i = self._next(i, end)
        return items

    def _at_top(self, i, items):
        return True  # brace groups at file scope are always orphans here


def parse_source(source: str):
    # Line continuations are lexical noise for the scanner: drop the
    # backslash but keep the newline, so token lines still match the file
    # (anchors are line ranges hashed against the real file). Directive
    # ranges are computed from the original text, before this stripping.
    stripped = source.replace("\\\r\n", "\n").replace("\\\n", "\n")
    # form feed (^L) is a page break, not a token
    stripped = stripped.replace("\x0c", " ")
    lexed = lex(stripped)
    pp_lines = _pp_lines(source.split("\n"))
    parser = CParser(lexed, pp_lines)
    items = parser.parse_items(0, len(lexed.tokens) - 1)
    return lexed, items, parser.unsupported


def parse_file(path: str):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return parse_source(fh.read())
