#!/usr/bin/env python3
"""Check markdown documents for undefined introduced terms.

The deterministic half of the "undefined introduced terms" rule: given a
repeated compound term, is it defined near its first use? Choosing the
candidates worth judging stays a human decision; this tool only measures.

The formula is fixed, so the number cannot be recomputed under a different
definition:

1. Text is scanned per file after removing fenced code blocks (``` / ~~~)
   and inline code spans (``...``): identifiers in code are not prose.
2. Words are maximal runs of letters (Cyrillic or Latin), at least 3 letters
   long. Digits and punctuation are not words.
3. A candidate term is 2 to 4 consecutive words on one line, separated by
   single spaces, none of which is a function word from the closed STOPWORDS
   list below. The whole phrase must occur at least 2 times in the file,
   case-insensitive; the most frequent casing is reported. A phrase used
   once is never flagged. Among flagged candidates, a phrase that is a
   contiguous sub-phrase of a longer flagged candidate with at least as
   many occurrences is not reported — only the maximal phrase is.
4. A term is DEFINED when the sentence holding its first occurrence matches
   any of these markers (case-insensitive):
   - the term followed by " — это" / " — это" variants ("X — это ...");
   - "под X понимается", "X означает", "X называется";
   - a parenthetical of 10+ characters immediately after the first use
     ("X (...механизм...)");
   - English: "X is ", "X are ", "X means", "X is defined as",
     "X refers to".
   Anything else is an undefined-term warning. The warning names the file,
   the first-use line, the term and the use count; it is a finding, not a
   proof of a violation — normal noun phrases repeat too.
5. The vocabulary file (--vocab, one term per line, `#` comments) marks
   established terms: a candidate equal to a vocabulary entry
   (case-insensitive) is never flagged. The vocabulary belongs to the
   project, not to this tool.

Exit codes: 0 ok, 1 --max-undefined exceeded (the only gate; it is not wired
into `make verify` until the noise of the rule is measured), 2 usage or
environment error.

STOPWORDS (closed list): и, в, во, не, на, с, со, а, но, то, же, из, за, по,
у, о, об, от, до, для, при, при, это, this, the, a, an, and, or, of, to, in,
on, for, with, is, are, was, were, be, that, it, its, as, by, at, from, not,
no.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

WORD = re.compile(r"[A-Za-zА-Яа-яЁё]+")

STOPWORDS = {
    "и", "в", "во", "не", "на", "с", "со", "а", "но", "то", "же", "из", "за",
    "по", "у", "о", "об", "от", "до", "для", "при", "это",
    "this", "the", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "be", "that", "it", "its", "as", "by", "at", "from",
    "not", "no",
}

MAX_WORDS = 4
MIN_WORDS = 2
MIN_USES = 2
MIN_PAREN = 10

FORMAT = "dev-sec-skills/term-check/1"


def strip_code(text: str) -> str:
    """Remove fenced blocks and inline code spans, keep line structure."""
    lines = []
    in_fence = False
    for line in text.splitlines():
        if re.match(r"\s*(```|~~~)", line):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else line)
    # inline spans may cross lines; replacing with same-length spaces keeps
    # every line number and column intact
    return re.sub(r"`[^`]*`",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  "\n".join(lines))


def words_of(line: str):
    """(word_lower, start, end) for every word of at least 3 letters."""
    return [(match.group(0).lower(), match.start(), match.end())
            for match in WORD.finditer(line) if len(match.group(0)) >= 3]


def candidate_phrases(text: str) -> dict:
    """phrase (lowercase) -> {"count": n, "lines": [(line_no, line)],
    "forms": {casing: n}} for every candidate of the fixed formula."""
    counts = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        words = words_of(line)
        for size in range(MIN_WORDS, MAX_WORDS + 1):
            for start in range(0, len(words) - size + 1):
                window = words[start:start + size]
                # consecutive words separated by exactly one space
                spaced = all(window[i][2] + 1 == window[i + 1][1]
                             for i in range(size - 1))
                if not spaced:
                    continue
                if window[0][0] in STOPWORDS or window[-1][0] in STOPWORDS:
                    continue
                phrase = " ".join(word for word, _, _ in window)
                form = line[window[0][1]:window[-1][2]]
                entry = counts.setdefault(phrase, {
                    "count": 0, "lines": [], "forms": {}})
                entry["count"] += 1
                entry["lines"].append((line_no, line))
                entry["forms"][form] = entry["forms"].get(form, 0) + 1
    return counts


def best_form(entry: dict) -> str:
    return sorted(entry["forms"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def sentence_at(line: str, start: int) -> str:
    """The sentence around the first use, cut on sentence punctuation."""
    boundaries = list(re.finditer(r"[.!?]\s", line[:start]))
    begin = boundaries[-1].end() if boundaries else 0
    right = re.search(r"[.!?](\s|$)", line[start:])
    end = start + (right.end() if right else len(line) - start)
    return line[begin:end]


DEFINITION_MARKERS = (
    "— это", "под {term} понимается", "{term} означает",
    "{term} называется", "{term} is ", "{term} are ", "{term} means",
    "{term} is defined as", "{term} refers to",
)


def is_defined(term: str, line: str, start: int) -> bool:
    """The fixed definition test from the docstring."""
    snippet = sentence_at(line, start)
    low = snippet.lower()
    for marker in DEFINITION_MARKERS:
        needle = marker.format(term=re.escape(term))
        if re.search(needle, low):
            return True
    # mechanism in parentheses right after the first use
    after = line[start + len(term):]
    if re.match(r"\s*\([^)]{%d,}\)" % MIN_PAREN, after):
        return True
    return False


def load_vocab(path: str) -> set:
    terms = set()
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#"):
                terms.add(line.lower())
    return terms


def _is_subphrase(short: list, long: list) -> bool:
    """True when `short` is a contiguous sub-phrase of `long`."""
    size = len(short)
    return any(long[i:i + size] == short
               for i in range(0, len(long) - size + 1))


def scan_file(path: str, vocab: set) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    text = strip_code(raw)
    flagged = []
    for phrase, entry in sorted(candidate_phrases(text).items()):
        if entry["count"] < MIN_USES:
            continue
        if phrase in vocab:
            continue
        first_line_no, first_line = entry["lines"][0]
        start = first_line.lower().find(phrase)
        if not is_defined(phrase, first_line, start):
            flagged.append((phrase, entry, {
                "file": path, "line": first_line_no, "term": best_form(entry),
                "uses": entry["count"],
            }))
    # maximal-phrase rule from the docstring: only the maximal flagged
    # phrase is reported, so a 4-word term does not flood the output with
    # its own sub-phrases.
    words = {phrase: phrase.split(" ") for phrase, _, _ in flagged}
    findings = []
    for phrase, entry, finding in flagged:
        swallowed = any(
            other != phrase
            and len(words[other]) > len(words[phrase])
            and entry["count"] <= other_entry["count"]
            and _is_subphrase(words[phrase], words[other])
            for other, other_entry, _ in flagged)
        if not swallowed:
            findings.append(finding)
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return findings


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Find repeated compound terms with no definition at "
                    "first use.")
    ap.add_argument("inputs", nargs="+", help="markdown files to scan")
    ap.add_argument("--vocab", help="vocabulary of established terms "
                                    "(one per line, # comments)")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--max-undefined", type=int, default=None,
                    help="fail when the warning count exceeds N "
                         "(the only gate; not wired into make verify)")
    args = ap.parse_args(argv)
    started = time.time()

    try:
        vocab = load_vocab(args.vocab) if args.vocab else set()
        for path in args.inputs:
            if not os.path.isfile(path):
                print("term-check: no such file: %s" % path, file=sys.stderr)
                return 2
        findings = []
        for path in args.inputs:
            findings.extend(scan_file(path, vocab))
    except (OSError, UnicodeDecodeError) as exc:
        print("term-check: %s" % exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps({
            "format": FORMAT,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": int((time.time() - started) * 1000),
            "inputs": list(args.inputs),
            "counts": {"undefined_terms": len(findings)},
            "findings": findings,
        }, ensure_ascii=False, indent=2))
    else:
        for finding in findings:
            print("term-check: %s:%d: undefined-term: '%s' "
                  "(%d uses; define at first use or describe the mechanism)"
                  % (finding["file"], finding["line"], finding["term"],
                     finding["uses"]))
        print("term-check: %d undefined term(s) in %d file(s)"
              % (len(findings), len(set(f["file"] for f in findings))))

    if args.max_undefined is not None and len(findings) > args.max_undefined:
        print("term-check: gate failed: %d > --max-undefined %d"
              % (len(findings), args.max_undefined), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
