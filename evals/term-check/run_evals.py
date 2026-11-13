#!/usr/bin/env python3
"""Adversarial eval runner for `term_check` (undefined introduced terms).

The tool's finding is a warning, not a proof of a violation: normal noun
phrases repeat too. The cases pin the fixed formula from the tool docstring
— what counts as a candidate, what counts as a definition — instead of
checking that "a warning appeared".

Cases:
  * a term defined at first use ("X — это ...") passes;
  * an undefined repeated term is flagged at its FIRST-use line, not the
    last one;
  * a term from the vocabulary file passes;
  * a single-use phrase is never flagged;
  * a mechanism in parentheses right after the first use counts as a
    definition;
  * a fenced code block is not prose: terms inside it are not candidates;
  * the negative control: an empty document must produce zero findings and
    exit 0 — a tool that flags the empty input is broken, and the runner
    must fail on it rather than pass vacuously;
  * the gate can actually fail: --max-undefined 0 with one finding exits 1.

Fixtures are synthetic and marked as such; they are not evidence about any
real document.

Usage:
    python3 evals/term-check/run_evals.py [--term-check PATH]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TOOL = os.path.join(REPO, "tools", "term_check.py")

if REPO not in sys.path and os.path.join(REPO, "tools") not in sys.path:
    pass  # the runner shells out; no import needed

DEFINED_DOC = """# Defined term

Языковая поддержка — это переключение каталогов при старте. Языковая
поддержка проверяется отдельными тестами.
"""

UNDEFINED_DOC = """# Undefined term

Эталонная контрольная сумма конфигурации записывается суперпозиторием один
раз. Эталонная контрольная сумма конфигурации сравнивается с текущим
состоянием после записи.
"""

VOCAB = """# established terms of the project
отказоустойчивость
"""

VOCAB_DOC = """# Vocabulary term

Отказоустойчивость проверяется тестами рестартов. Отказоустойчивость
описана в другом разделе.
"""

SINGLE_USE_DOC = """# Single use

Одноразовый термин здесь употреблён один раз и не кандидат.
"""

PAREN_DOC = """# Parenthetical mechanism

Отказоустойчивость (механизм: рестарты и реплики) описана в другом разделе.
Отказоустойчивость покрывается тестами рестартов.
"""

CODE_DOC = """# Code is not prose

Неопределённый составной термин в коде не считается: `неопределённый
составной термин` живёт в backticks ниже.

```
неопределённый составной термин в блоке
```

Неопределённый составной термин повторяется в прозе.
"""

EMPTY_DOC = ""

# The fenced block and the multi-line code span are stripped; the first
# prose use of the term is line 3, and the span on lines 3-4 adds nothing.
CODE_FIRST_LINE = 3

# The undefined phrase first occurs on line 3 (after the heading and the
# blank line). The warning pins the first-use line, not the later one.
UNDEFINED_FIRST_LINE = 3


def run_tool(tool, root, files, args):
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    return subprocess.run([sys.executable, tool] + args,
                          capture_output=True, text=True, cwd=root)


CASES = [
    {
        "name": "a term defined at first use passes",
        "files": {"doc.md": DEFINED_DOC},
        "args": ["doc.md"],
        "exit": 0,
        "forbids": ["undefined-term"],
    },
    {
        "name": "an undefined repeated term is flagged at its first use",
        "files": {"doc.md": UNDEFINED_DOC},
        "args": ["doc.md"],
        "exit": 0,
        "contains": ["doc.md:%d: undefined-term" % UNDEFINED_FIRST_LINE,
                     "Эталонная контрольная сумма конфигурации",
                     "2 uses"],
    },
    {
        "name": "a vocabulary term passes",
        "files": {"doc.md": VOCAB_DOC, "vocab.txt": VOCAB},
        "args": ["--vocab", "vocab.txt", "doc.md"],
        "exit": 0,
        "forbids": ["undefined-term"],
    },
    {
        "name": "a single-use phrase is never flagged",
        "files": {"doc.md": SINGLE_USE_DOC},
        "args": ["doc.md"],
        "exit": 0,
        "forbids": ["undefined-term"],
        "contains": ["0 undefined term(s)"],
    },
    {
        "name": "a parenthetical mechanism counts as a definition",
        "files": {"doc.md": PAREN_DOC},
        "args": ["doc.md"],
        "exit": 0,
        "forbids": ["undefined-term"],
    },
    {
        "name": "code blocks and backticks are not prose",
        "files": {"doc.md": CODE_DOC},
        "args": ["doc.md"],
        "exit": 0,
        "contains": ["doc.md:%d: undefined-term" % CODE_FIRST_LINE],
        # the multi-line span must not add a third use of the sub-phrase:
        # a finding of 'составной термин' alone means the span leaked
        "forbids": ["в блоке", "'составной термин'"],
    },
    {
        "name": "negative control: an empty document yields no findings",
        "files": {"empty.md": EMPTY_DOC},
        "args": ["empty.md"],
        "exit": 0,
        "contains": ["0 undefined term(s)"],
        "forbids": ["undefined-term:"],
    },
    {
        "name": "the gate can actually fail",
        "files": {"doc.md": UNDEFINED_DOC},
        "args": ["--max-undefined", "0", "doc.md"],
        "exit": 1,
        "contains": ["gate failed"],
    },
    {
        "name": "the json format pins file, line and count",
        "files": {"doc.md": UNDEFINED_DOC},
        "args": ["--format", "json", "doc.md"],
        "exit": 0,
        "json": {
            "counts": {"undefined_terms": 1},
            "findings": [{"file": "doc.md",
                          "line": UNDEFINED_FIRST_LINE,
                          "uses": 2}],
        },
    },
    {
        "name": "a missing file is an environment error, not a finding",
        "files": {},
        "args": ["no-such-file.md"],
        "exit": 2,
        "contains": ["no such file"],
    },
]


def run_case(case, root, tool):
    proc = run_tool(tool, root, case["files"], case["args"])
    problems = []
    if proc.returncode != case["exit"]:
        problems.append("exit %d, expected %d\n%s\n%s"
                        % (proc.returncode, case["exit"],
                           proc.stdout[-500:], proc.stderr[-500:]))
    # stderr counts too: the gate message and environment errors are
    # written there, and a case must be able to pin them.
    lines = proc.stdout.splitlines() + proc.stderr.splitlines()
    for needle in case.get("contains", []):
        if not any(needle in line for line in lines):
            problems.append("stdout lacks %r" % needle)
    for needle in case.get("forbids", []):
        if any(needle in line for line in lines):
            problems.append("stdout contains %r" % needle)
    if "json" in case:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            problems.append("stdout is not json: %s" % exc)
            return problems
        expected_counts = case["json"].get("counts") or {}
        for key, value in expected_counts.items():
            got = (payload.get("counts") or {}).get(key)
            if got != value:
                problems.append("counts.%s: %r, expected %r"
                                % (key, got, value))
        for expected in case["json"].get("findings") or []:
            found = any(
                all(finding.get(key) == value
                    for key, value in expected.items())
                for finding in payload.get("findings") or [])
            if not found:
                problems.append("no finding matches %r in %r"
                                % (expected, payload.get("findings")))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--term-check", default=DEFAULT_TOOL)
    args = ap.parse_args()

    failed = 0
    for case in CASES:
        root = tempfile.mkdtemp(prefix="term-check-eval-")
        try:
            problems = run_case(case, root, args.term_check)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            failed += 1
            print("FAIL %s" % case["name"])
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % case["name"])
    print("%d/%d term-check eval cases passed"
          % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
