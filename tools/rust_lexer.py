#!/usr/bin/env python3
"""A hand-written Rust lexer: enough structure to anchor model primitives.

This is not a parser and does not pretend to be one. It produces a token stream
with byte offsets and line numbers, and it gets four things right that a regex
cannot:

* block comments nest (``/* /* */ */``);
* raw strings ``r"..."``, ``r#"..."#``, ``br##"..."##`` end at the matching
  number of hashes, not at the first quote;
* char literals and lifetimes are distinguishable (``'a'`` vs ``'a``);
* byte strings and byte chars (``b"..."``, ``b'a'``) are not identifiers.

Anything it cannot scan raises :class:`LexError` with a line and column; the
caller records that file as ``unmapped`` instead of guessing.
"""

from __future__ import annotations

IDENT = "ident"
LIFETIME = "lifetime"
STR = "str"
CHAR = "char"
NUM = "num"
PUNCT = "punct"
DOC = "doc"
EOF = "eof"

_PUNCT = (
    "::", "->", "=>", "..=", "...", "..", "==", "!=", "<=", ">=",
    "&&", "||", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|=",
    "(", ")", "[", "]", "{", "}", "<", ">", ",", ";", ":", ".",
    "+", "-", "*", "/", "%", "^", "&", "|", "!", "~", "?", "@", "#", "$", "=",
)

_OPEN = {"(": ")", "[": "]", "{": "}"}


class LexError(Exception):
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__("%s at %d:%d" % (message, line, column))


class Token:
    __slots__ = ("kind", "text", "start", "end", "line", "column")

    def __init__(self, kind, text, start, end, line, column):
        self.kind = kind
        self.text = text
        self.start = start
        self.end = end
        self.line = line
        self.column = column

    def __repr__(self):
        return "Token(%s, %r, line=%d)" % (self.kind, self.text, self.line)

    def is_(self, text: str) -> bool:
        return self.text == text


class Lexed:
    """The result: tokens, doc comments and the bracket map."""

    def __init__(self, source, tokens, doc_comments, pairs, lines):
        self._source = source
        self.tokens = tokens
        self.doc_comments = doc_comments
        self.pairs = pairs          # token index -> matching bracket index
        self.lines = lines          # 1-based line -> text

    def text_between(self, first: int, last: int) -> str:
        """Source text spanned by token indices ``first..last`` (inclusive)."""
        if first > last:
            return ""
        return self._source[self.tokens[first].start:self.tokens[last].end]

    def line_text(self, line: int) -> str:
        return self.lines[line - 1] if 1 <= line <= len(self.lines) else ""


def _is_ident_start(ch: str) -> bool:
    return ch == "_" or ch.isalpha()


def _is_ident_continue(ch: str) -> bool:
    return ch == "_" or ch.isalnum()


class _Scanner:
    def __init__(self, source: str):
        self.s = source
        self.n = len(source)
        self.i = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.docs = []

    # -- position ---------------------------------------------------------

    def _advance(self, count: int = 1) -> None:
        for _ in range(count):
            if self.i >= self.n:
                return
            if self.s[self.i] == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.i += 1

    def _emit(self, kind: str, start: int, start_line: int, start_col: int):
        token = Token(kind, self.s[start:self.i], start, self.i,
                      start_line, start_col)
        self.tokens.append(token)
        if kind == DOC:
            self.docs.append(token)
        return token

    # -- scanners ---------------------------------------------------------

    def _skip_block_comment(self) -> bool:
        """Consume a nested block comment; return True when it was a doc."""
        s, start = self.s, self.i
        is_doc = (s.startswith("/**", start) and not s.startswith("/**/", start))
        start_line, start_col = self.line, self.col
        self._advance(2)
        depth = 1
        while self.i < self.n:
            if s.startswith("/*", self.i):
                depth += 1
                self._advance(2)
            elif s.startswith("*/", self.i):
                depth -= 1
                self._advance(2)
                if depth == 0:
                    break
            else:
                self._advance()
        if depth:
            raise LexError("unterminated block comment", start_line, start_col)
        if is_doc:
            self._emit(DOC, start, start_line, start_col)
        return True

    def _skip_line_comment(self) -> None:
        s, start = self.s, self.i
        start_line, start_col = self.line, self.col
        is_doc = (s.startswith("///", start) and not s.startswith("////", start)) \
            or s.startswith("//!", start)
        while self.i < self.n and s[self.i] != "\n":
            self._advance()
        if is_doc:
            self._emit(DOC, start, start_line, start_col)

    def _scan_string(self, prefix_len: int) -> None:
        """Normal string after an optional b/c prefix of ``prefix_len``."""
        s = self.s
        start = self.i
        start_line, start_col = self.line, self.col
        self._advance(prefix_len)      # prefix
        self._advance()                # opening quote
        while self.i < self.n:
            ch = s[self.i]
            if ch == "\\":
                self._advance(2)
                continue
            if ch == '"':
                self._advance()
                break
            self._advance()
        else:
            raise LexError("unterminated string literal", start_line, start_col)
        self._emit(STR, start, start_line, start_col)

    def _scan_raw_string(self, prefix_len: int, hashes: int) -> None:
        s = self.s
        start = self.i
        start_line, start_col = self.line, self.col
        self._advance(prefix_len)      # b/c/r
        self._advance(hashes)          # '#'
        self._advance()                # opening quote
        closing = '"' + "#" * hashes
        while self.i < self.n:
            if s.startswith(closing, self.i):
                self._advance(len(closing))
                break
            self._advance()
        else:
            raise LexError("unterminated raw string", start_line, start_col)
        self._emit(STR, start, start_line, start_col)

    def _escape_end(self, at: int) -> int:
        """Index just after the escape sequence that starts at ``at`` (\\)."""
        s = self.s
        j = at + 1
        if j >= self.n:
            return j
        ch = s[j]
        if ch == "x":
            return min(j + 3, self.n)
        if ch == "u" and j + 1 < self.n and s[j + 1] == "{":
            k = j + 2
            while k < self.n and s[k] != "}":
                k += 1
            return min(k + 1, self.n)
        return j + 1

    def _scan_quote(self) -> None:
        """Either a char literal (``'a'``, ``'\\n'``) or a lifetime (``'a``)."""
        s, start = self.s, self.i
        start_line, start_col = self.line, self.col
        j = start + 1
        if j >= self.n:
            raise LexError("dangling quote", start_line, start_col)
        if s[j] == "\\":
            end = self._escape_end(j)
            if end < self.n and s[end] == "'":
                self._advance(end + 1 - start)
                self._emit(CHAR, start, start_line, start_col)
                return
            # an escaped lifetime does not exist; treat as lifetime-ish
            self._advance()
            self._emit(LIFETIME, start, start_line, start_col)
            return
        if j + 1 < self.n and s[j + 1] == "'" and s[j] != "'":
            self._advance(3)
            self._emit(CHAR, start, start_line, start_col)
            return
        # lifetime: ' + ident
        k = j
        while k < self.n and _is_ident_continue(s[k]):
            k += 1
        if k == j:                       # a lone quote
            raise LexError("unexpected quote", start_line, start_col)
        self._advance(k - start)
        self._emit(LIFETIME, start, start_line, start_col)

    def _scan_prefixed(self) -> bool:
        """b\"...\", b'x', c\"...\", r\"...\", r#\"...\", br#\"...\"."""
        s, i, n = self.s, self.i, self.n
        j = i
        prefix = 0
        if s[j] in ("b", "c") and j + 1 < n:
            prefix = 1
            j += 1
        if j >= n:
            return False
        if s[j] == "r":
            k = j + 1
            hashes = 0
            while k < n and s[k] == "#":
                hashes += 1
                k += 1
            if k < n and s[k] == '"':
                self._scan_raw_string(prefix + 1, hashes)
                return True
            # r#ident is a raw identifier
            if prefix == 0 and hashes == 1 and k < n and _is_ident_start(s[k]):
                start, start_line, start_col = self.i, self.line, self.col
                self._advance(2)
                while self.i < self.n and _is_ident_continue(s[self.i]):
                    self._advance()
                self._emit(IDENT, start, start_line, start_col)
                return True
            if prefix:
                return False
            return False
        if s[j] == '"':
            self._scan_string(prefix)
            return True
        if prefix and s[j] == "'":
            # byte char: b'a'
            start, start_line, start_col = self.i, self.line, self.col
            end = self._escape_end(j + 1) if j + 1 < n and s[j + 1] == "\\" \
                else j + 2
            if end < n and s[end] == "'":
                self._advance(end + 1 - start)
                self._emit(CHAR, start, start_line, start_col)
                return True
            raise LexError("unterminated byte char", self.line, self.col)
        return False

    def _scan_number(self) -> None:
        s, start = self.s, self.i
        start_line, start_col = self.line, self.col
        self._advance()
        while self.i < self.n:
            ch = s[self.i]
            if ch.isalnum() or ch == "_":
                self._advance()
            elif ch == "." and self.i + 1 < self.n and s[self.i + 1].isdigit():
                self._advance()
            else:
                break
        self._emit(NUM, start, start_line, start_col)

    def _scan_ident(self) -> None:
        start, start_line, start_col = self.i, self.line, self.col
        self._advance()
        while self.i < self.n and _is_ident_continue(self.s[self.i]):
            self._advance()
        self._emit(IDENT, start, start_line, start_col)

    def _scan_punct(self) -> None:
        s, start = self.s, self.i
        start_line, start_col = self.line, self.col
        for op in _PUNCT:
            if s.startswith(op, self.i):
                self._advance(len(op))
                self._emit(PUNCT, start, start_line, start_col)
                return
        raise LexError("unexpected character %r" % s[self.i],
                       self.line, self.col)

    # -- main -------------------------------------------------------------

    def run(self) -> Lexed:
        s = self.s
        while self.i < self.n:
            ch = s[self.i]
            if ch in " \t\r\n":
                self._advance()
                continue
            if s.startswith("//", self.i):
                self._skip_line_comment()
                continue
            if s.startswith("/*", self.i):
                self._skip_block_comment()
                continue
            if ch == '"':
                self._scan_string(0)
                continue
            if ch == "'":
                self._scan_quote()
                continue
            if ch in ("b", "c", "r") and self._scan_prefixed():
                continue
            if ch.isdigit():
                self._scan_number()
                continue
            if _is_ident_start(ch):
                self._scan_ident()
                continue
            self._scan_punct()

        self.tokens.append(Token(EOF, "", self.n, self.n, self.line, self.col))
        pairs = _bracket_map(self.tokens)
        lines = s.split("\n")
        return Lexed(s, self.tokens, self.docs, pairs, lines)


def _bracket_map(tokens):
    """Token index -> index of the matching bracket, for (), [] and {}."""
    pairs = {}
    stack = []
    for idx, token in enumerate(tokens):
        if token.kind != PUNCT:
            continue
        if token.text in _OPEN:
            stack.append((idx, token.text))
        elif token.text in (")", "]", "}"):
            if not stack:
                raise LexError("unbalanced %r" % token.text,
                               token.line, token.column)
            open_idx, open_text = stack.pop()
            if _OPEN[open_text] != token.text:
                raise LexError(
                    "mismatched brackets: %r closed by %r"
                    % (open_text, token.text), token.line, token.column)
            pairs[open_idx] = idx
            pairs[idx] = open_idx
    if stack:
        open_idx, open_text = stack[-1]
        token = tokens[open_idx]
        raise LexError("unclosed %r" % open_text, token.line, token.column)
    return pairs


def lex(source: str) -> Lexed:
    return _Scanner(source).run()


def lex_file(path: str) -> Lexed:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return lex(fh.read())
