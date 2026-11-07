# Choke-Point Extraction

`tools/choke_points.py` (V2-22) answers a different question from
`spec/diff-coverage/`: not "did a declared choke point change under a claim?"
but "which definitions in ordinary code look like enforcement sites, and which
cell class would each one belong to?"

It is a review queue. A candidate is a reason to look at a definition. A class
match is a hypothesis, not evidence that the definition enforces an invariant,
and not a cell. Nothing here runs tests, proves a property or changes a registry.

## Inputs

- `spec/choke-points/rules.yaml` — `signals` decide whether a definition is a
  candidate; `rules` map a candidate to `taxonomy_class`, `failure_class` and
  `failure_mode` from `spec/conveyor/cell-registry.schema.json`.
- `--schema` — the registry schema; when supplied, the rules are validated
  against its `taxonomy_class` and `failure_mode` enums before any scan.
- `--root` — the tree to scan. Default globs are `*.py`, `*.rs`, `*.sql`;
  `--glob` can narrow or widen them.

Rules are ordered and the first match wins, so a narrow rule must precede a
broad one. Within one rule the fields are OR-ed: a rule that names both `kind`
and `name` matches when either matches. That is why `sql-rls` matches on `kind`
alone — a `CREATE POLICY tenant_isolation ...` statement has no word "policy" in
its extracted name, and a Python function named `check_access` must not be
classified as RLS because its name contains `access`.

A candidate that matches a signal but no rule is reported as `unclassified`.
It is not forced into `other`: `other` is a cell escape hatch that requires a
`routing_note` and is counted by `tools/unroutable.py`, while an unclassified
scan result is a gap in the rules file. A rule that maps to `other` is rejected
as a usage error.

## Extraction

| Extension | How a definition and its span are found |
| --- | --- |
| `.py` | standard-library `ast`; `def`, `async def`, `class`; the span starts at the first decorator and ends at `end_lineno` |
| `.rs` | a lexer for `//`, nested `/* */`, strings, raw/byte strings and char literals, then `fn` and brace matching; preceding contiguous `#[...]` attribute lines join the span |
| `.sql` | a lexer for `--`, nested `/* */`, `''`, `""` and `$tag$...$tag$`, then statements split on top-level `;`; the span covers the whole `CREATE/DROP/ALTER ...;` statement |
| anything else | skipped and counted; never guessed |

The Python path is a real parser. The Rust and SQL paths are structural
lexers, not full grammar parsers: they are comment- and string-aware and they
find braces or statement boundaries, but they do not build a syntax tree. That
distinction is deliberate and is repeated in the limits below.

Because a SQL span is the whole statement, an edit inside a dollar-quoted body
is attributed to the function even when the diff never repeats its name. Because
the Rust lexer blanks block comments and char literals, a `}` in `/* } */` or
`let c = '}';` does not close the function early. Because the Python span starts
at the decorator, editing only `@require_permission(...)` changes the symbol.

## Checks

| Check | Default | Fires when |
| --- | --- | --- |
| CP1 unclassified | unset | more candidates than `--max-unclassified` match no rule |
| CP2 parse errors | unset | more files than `--max-parse-errors` cannot be parsed |

Both thresholds default to unset. The scan prints the counts either way; a
threshold turns the count into an error. CP1 is not in `make verify`: there is a
measurement but no agreed ceiling, and a review queue should not be a merge gate
while a large share of its candidates has no rule.

Exit codes: `0` no error, `1` a threshold was exceeded, `2` tool or input error.

`--list` prints every candidate. `--json` writes the full result, including
every candidate with its span, decorators, calls, matched signals, rule,
`matched_field` and the evidence text that matched.

## Measured 2026-11-07

Snapshots are written by `make choke-points-record`.

| Pilot | Files | Definitions | Candidates | Classified | Unclassified | Security | Correctness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rbac_pg` | 75 (44 py, 31 sql) | 1585 | 1413 | 867 (61.4 %) | 546 (38.6 %) | 808 | 59 |
| `craft-i18n` | 9 (4 py, 5 rs) | 128 | 64 | 47 (73.4 %) | 17 (26.6 %) | 25 | 22 |
| both | 84 | 1713 | 1477 | 914 (61.9 %) | 563 (38.1 %) | 833 | 81 |

Artifacts:

- `2026-11-07-rbac-pg.json`
- `2026-11-07-craft-i18n.json`

By language the candidates split as Python 306, SQL 1148, Rust 23. The SQL
share dominates because `sql-object` makes every extracted SQL function a
candidate even when its name and body contain no guard word.

The unclassified share is not hidden and is not a taxonomy class. Its shape:

- `rbac_pg`: 454 SQL functions, 81 Python functions, 11 methods. 419 candidates
  carry only `sql-object`; 90 carry only `guard-call` (generic calls such as
  `connect`, `emit` or `read`); 29 carry `guard-name` plus `sql-object`; 6 carry
  `guard-call` plus `sql-object`.
- `craft-i18n`: 17 functions/methods, all with only `guard-call` — mostly test
  helpers that call `read` or `write`.

These are rule gaps as measured, not a bug to paper over with a catch-all rule.
The honest next step is either a narrower `guard-call` signal (a sink call is not
a guard call) or more specific class rules, each justified independently. Until
then the threshold stays off.

## Negative controls

- `evals/choke-points/` — 14 cases, all passing: Python decorator spans and a
  `def` inside a docstring; a syntax error counted and CP2 red; Rust comments,
  raw strings, char literals and a block-comment brace; SQL dollar-quoted bodies
  with internal semicolons; SQL definitions inside comments; rule precedence
  (first match wins); unclassified reported and CP1 red at zero; the same
  candidate green at a threshold of one; `taxonomy_class: other` rejected;
  unknown taxonomy and failure-mode enums rejected; unknown extensions skipped;
  a missing root and a missing rules file returning 2.
- The Python case asserts the start line is the decorator (`3`), so an
  indentation scanner that starts at `def` cannot pass it.
- The Rust case puts `}` in a block comment before the changed body line, so a
  brace counter that ignores block comments closes the span early and fails.
- The SQL body case changes `PERFORM 1` to `PERFORM 2` without naming the
  function; a name-only scanner sees nothing.
- The comment cases assert that `fake`, `fake_policy` and a comment-mentioned
  symbol do not appear as candidates.
- `evals/diff-coverage/` grew to 19 cases for the integration: a SQL body-only
  edit, a Rust block-comment brace, a Python decorator-only change, a
  comment-only mention that the fallback must not treat as a symbol change, and
  a head file whose definitions shift down so head line numbers are not applied
  to the base blob. All pass, and the previous 14 still pass.
- On the real pilots `make diff-coverage` still maps 2/2 entities in each range,
  so the stricter extractor did not lose the two declared choke points.

## Reproduce

```bash
python3 evals/choke-points/run_evals.py
make choke-points            # print both pilot scans
make choke-points-record     # rewrite the two JSON snapshots
python3 evals/diff-coverage/run_evals.py
make diff-coverage
```

## Limits

- Signals and rules are regular expressions over a name, the calls in a body,
  decorators, the path and the kind. They do not understand semantics, data
  flow or whether a guard is actually on the path.
- The Rust extractor is a lexer. Macros that generate functions, functions
  produced by `include!` and unusual const-generic braces can confuse spans;
  duplicate simple names are independent entries.
- The SQL extractor splits on top-level semicolons outside literals. A
  `BEGIN ATOMIC ...; ...` body keeps its internal semicolons only insofar as the
  outer statement terminator is recognized; quoted identifiers are skipped by
  the definition patterns. PL/pgSQL bodies are not parsed.
- Python is the only path backed by a full parser. An unparsable Python file is
  counted as a parse error and contributes no definitions; it is not partially
  recovered. `masked_lines_for` falls back to raw lines when tokenization fails.
- A `guard-call` signal currently treats a sink call (`read`, `write`,
  `execute`) like a guard call, which inflates candidates and the unclassified
  share. That is visible in the measurement above rather than tuned away.
- A class match is a hypothesis. Promoting a reviewed site to a cell still
  requires the registry's own fields, evidence and status rules.
- The measurement covers two repositories and one rules file on one date. A
  different codebase can have a different unclassified share, and no threshold
  is claimed to be portable.
