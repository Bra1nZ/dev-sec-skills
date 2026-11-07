# Diff Coverage

`tools/diff_coverage.py` (V2-07) answers a narrow question: when a declared
choke point changed between two commits, does a non-open claim cover it?

It reads one cell registry, one claim ledger and a git range. It does not run
tests, does not check that a claim is true, and does not prove the changed code
is correct. A clean run means every changed declaration was mapped; a red run
means at least one changed declaration had no claim behind it.

## Checks

| Check | Severity | Fires when |
| --- | --- | --- |
| DC1 path | info | a declared choke-point path changed and no non-open claim maps it |
| DC2 symbol | info | a symbol named in `enforced_at` changed and no non-open claim maps it |
| DC3 declaration | **error** | `enforced_at` cannot be located in the repository |
| DC4 empty diff | info | the range contains no changed declared choke point |
| DC5 empty registry | info | the registry declares no `enforced_at` at all |

DC1 and DC2 become errors only when the number of unmapped entities exceeds
`--max-unmapped`, which defaults to `0`. The threshold is aggregate: it counts
changed paths plus changed symbols, not each kind separately. Below the
threshold an unmapped entity is still printed with `UNMAPPED`; a policy that
tolerates one unmapped path does not make it covered.

DC3 is always an error and has three causes, all fail-closed:

- the value has no leading `path:line` (for example, prose such as "the guard in
  the API layer");
- the path is absent as a blob at both base and head (a directory also fails,
  because the check is `git cat-file -t <sha>:<path>` = `blob`);
- the path escapes the repository root (`..`, or an absolute path).

DC4 and DC5 are informational: a range that touches nothing declared, or a
registry that declares nothing, cannot produce a meaningful share. The run is
green in both cases, and prints why.

Exit codes: `0` no errors, `1` errors, `2` tool or usage error. A base ref that
does not resolve is `2`, not an empty green diff.

## What counts as mapped

`enforced_at` is the only source of choke points. Entry points, detectors and
mutation fixtures are not used: an entry point names where a caller enters, not
where the property is enforced.

A changed path maps when either holds:

- a cell that declares the path carries a `claim_ids` entry that resolves to a
  non-open claim in the ledger;
- a non-open claim's evidence `artifact` normalises to the declared path.

A changed symbol maps when either holds:

- a cell that declares the symbol carries a `claim_ids` entry that resolves to a
  non-open claim;
- a non-open claim's evidence `tests` (or a detector's `negative_test`) cites
  the symbol literally.

`open` claims are excluded from every mapping. An open claim is a plan, not
coverage; a cell that links only to an open claim stays unmapped.

The two rules are independent on purpose. A cell may link a claim that names a
different artifact; a claim may name the artifact without being linked from the
cell. Both paths are visible, and the report lists the claims that mapped each
entity.

## Extractor, and its boundaries

Symbols are extracted by a line scanner, not an AST:

| Extension | How the span is found |
| --- | --- |
| `.py` | `def` / `class` at any indentation; the span ends at the first non-blank, non-comment line indented at or below the definition |
| `.rs` | `fn`; brace depth from the definition, with `//` comments and string literals stripped |
| everything else (SQL, unknown) | no span; the symbol counts when its name appears on an added or removed line |

Consequences that are real and not hypothetical:

- A Python body-only edit is caught even when the diff never repeats the
  function name, because the changed line falls inside the indentation span.
- A Rust body-only edit is caught the same way, unless a brace inside a block
  comment or a character literal breaks the depth count. Those forms are not
  stripped.
- A SQL body-only edit is **not** caught: if the changed lines never mention the
  function name, no span exists to place them in. Adding `CREATE OR REPLACE
  FUNCTION` or an `ALTER` line catches it; changing one expression inside the
  body does not. This is the gap V2-22 (an AST/parser extractor) is meant to
  close.
- A decorator or an attribute line above a Python definition is outside the
  span; changing only the decorator does not count as changing the symbol. The
  path still changes, so DC1 still sees the file.
- A symbol named in `enforced_at` is the first identifier after `FUNCTION `, or
  otherwise the first identifier inside `(`. A declaration written as
  `path:12 - the guard` has a path but no symbol; only the path is checked.
- Renames are followed: the old side of a rename is treated as the declared
  path, so a choke point that moved is still located.

The scanner errs toward false positives when it falls back to name matching: a
symbol name that appears in a comment or an unrelated string on a changed line
counts as changed. That direction is deliberate — the gate exists to force a
mapping, and a false positive costs a claim link, while a false negative hides a
changed choke point.

## Measured 2026-11-07

Both ranges are fixed measurements, not PR ranges. Snapshots are written by
`make diff-coverage-record`.

| Pilot | Range | Changed files | Declared | Changed | Mapped | Share |
| --- | --- | --- | --- | --- | --- | --- |
| `rbac_pg` | `v1.3.1..HEAD` (`6141639..d978609`) | 110 | 1 path, 1 symbol | 2 | 2 | 100 % |
| `craft-i18n` | `f0dd77b^..f0dd77b` (`17906c5..f0dd77b`) | 3 | 1 path, 1 symbol | 2 | 2 | 100 % |

Artifacts:

- `2026-11-07-rbac-pg.json`
- `2026-11-07-craft-i18n.json`

The `rbac_pg` result is `sql/rbac--1.7.sql` and
`rbac.apply_policy_document`, both mapped to C-01 through CELL-001. The
`craft-i18n` result is `crates/craft-i18n-tests/src/catalog.rs` (mapped to
C-01/C-02/C-03) and `parse_row` (C-01/C-02).

The 100 % share is not registry coverage. Of 29 `rbac_pg` cells, only CELL-001
declares `enforced_at`, and of 14 `craft-i18n` cells, only CELL-003 does. The
measurement covers those two declarations, not the other 41 cells. V2-07 checks
the declarations that exist; it does not force a cell to declare one. A registry
that declares nothing gets DC5 and a green run.

The `rbac_pg` range is deliberately wide against a single declaration: 110 files
changed and one declared choke point. That shows the gate does not drown in
unrelated files, but it says nothing about the other 28 cells.

## Negative controls

- `evals/diff-coverage/` — 14 cases: clean path and symbol, unmapped path,
  unmapped symbol, symbol mapped only by a test ID, untouched choke point (DC4),
  missing declaration path, prose declaration, open claim excluded, deleted
  file, added SQL symbol, no declarations (DC5), threshold that tolerates one
  unmapped entity, renamed file, and a missing ref (exit 2). All pass.
- The clean control asserts `share = 1.0` and both entities mapped, so a tool
  that always reports zero cannot pass the suite.
- Removing `claim_ids` from CELL-001 in a copy of the `rbac_pg` registry under
  `/tmp` makes both entities unmapped, DC1 and DC2 error, exit 1. The repository
  registry is not modified.
- Removing `claim_ids` from CELL-003 in a copy of the `craft-i18n` registry
  leaves the path mapped through C-02/C-03 (`artifact` names the file) but
  leaves `parse_row` unmapped: DC2 errors, exit 1. This is the independent
  mapping rule working as specified.
- `--max-unmapped 1` on one unmapped entity reports it and exits 0, so the
  threshold is exercised rather than assumed.

## CI template

`ci/diff-coverage.yml` is a PR gate, not part of `make verify`. `verify`
compares this repository's working tree against the last commit, and a diff
coverage gate needs the PR base SHA. The template:

- checks out with `fetch-depth: 0`;
- resolves the merge base of the base branch and the PR head, and diffs that
  merge base against `github.event.pull_request.head.sha`;
- runs with `--max-unmapped 0`, so any changed declaration without a claim
  fails the job;
- points `CELLS` and `LEDGER` at the target repository's files, because the
  registry used here lives in `dev-sec-skills`, not in the pilot.

## Limits

- Mapping is not freshness. A claim may be mapped and still be stale or false;
  CV3 in `spec/coverage/` measures freshness, and neither check proves the
  claim.
- Only cells with `enforced_at` participate. The gate cannot report that a cell
  omitted the declaration.
- The extractor is a scanner. SQL body-only changes, decorators, macros and
  generated code are invisible or only partially visible (V2-22).
- The token fallback can mark a symbol changed because its name appeared in a
  comment or a string; that is a false positive by design.
- The share counts entities, not the amount of changed code. One changed symbol
  and a thousand changed lines weigh the same.
- The range is whatever the caller passes. `v1.3.1..HEAD` is a measurement
  range; a PR gate must pass the PR merge base (or the base tip) rather than a
  release tag, and a force-push rewrites the comparison.
- No real PR has run through this gate yet: the template is untested against a
  target repository's branch protection. The recorded runs are manual.
