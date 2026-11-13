# Undefined Introduced Terms

A technical term is a claim about the domain: it says "this concept exists
here and is established". When a compound term is used as if everyone already
knows it — but it is not an established domain term and is never defined at
first use — the reader cannot tell a coinage from standard terminology. A
term-label left undefined is naming, not explaining.

Use this list before publishing technical documentation, next to
`banned-words.md`.

## Rule

A compound technical term (2+ words, a noun phrase) may be used without
quotation marks or introduction markers only when at least one holds:

1. it is an established term of the domain (the domain's vocabulary or
   standard names it), or
2. the first use defines it — "X — это", "под X понимается", "X означает",
   "X называется", a mechanism in parentheses or in the adjacent sentence;
   English: "X is", "X means", "X is defined as", "X refers to".

Otherwise define the term at first use or describe the mechanism next to it.
Do not invent a mechanism the text does not contain.

## Worked example

From a real review (roles document, 2026-11-09): the phrase «эталон
целостности» was used five times as if it were an established term, with no
definition. The mechanism did exist — in another section: the superuser
records a checksum of the configuration once (`record_integrity_baseline`),
and the current state is compared against it; before that record, no
comparison happens.

- Bad: «эталон целостности» — five uses, no definition; a reader cannot tell
  it from a standard term.
- Good: «эталонная контрольная сумма конфигурации не создаётся автоматически —
  суперпользователь один раз записывает её вручную, и с ней сравнивается
  текущее состояние» — the term is defined through the mechanism the text
  already describes.

## Decision card

**Apply:** check whether the term is established in the domain, and whether
the first use defines it. An established term, or a term defined at first
use, stays.

**Edit:** «эталон целостности не записывается сам» → «эталонная контрольная
сумма конфигурации не создаётся автоматически — суперпользователь один раз
записывает её вручную, и с ней сравнивается текущее состояние». The term is
defined through the mechanism the text already describes.

**Keep:** «RLS не может позволить запись роли, которой не выдан UPDATE» — an
established domain term. A term defined at first use is then used as-is.

**Flag a gap:** if the fix needs a fact the text does not contain (what
exactly is compared, who records it), report the gap — do not invent a
mechanism.

## Method boundaries

- Telling a coinage from an established term is only possible with a domain
  vocabulary or judgment; a fully deterministic detector of "all undefined
  terms" does not exist.
- A repeated compound term without a definition nearby is a finding, not a
  proof of a violation: normal noun phrases repeat too. Machine output is a
  warning (`term_check.py`), and the decision above is applied by judgment.
- One-off labels are not caught by repetition at all; they are caught by the
  decision card only.
