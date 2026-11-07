# Coverage Report

`tools/coverage_report.py` (V2-20) reads one cell registry, optionally its claim
ledger, and the target suite, and reports four things the registries can hide:

- **CV1 mapping** — a cited symbol (a claim's `tests` item, a detector's
  `negative_test`) does not exist in the suite. Always an error.
- **CV2 symbols** — suite symbols that no artifact, claim or negative test
  maps. Reported with their files; an error only when `--max-unmapped` is
  exceeded.
- **CV3 stale claims** — non-open claims whose latest date is missing or older
  than `--max-age-days` (default 90). Info by default, an error only with
  `--max-stale-claims`.
- **CV4 no fixture** — non-open `test` / `runtime-enforcement` detectors with
  neither `mutation_fixture` nor `mutation_exemption`. Info by default, an
  error only with `--max-cells-without-fixture`.

Exit codes: `0` no errors, `1` errors, `2` tool or usage error.

## Method, and what it deliberately does not do

Without `--suite-glob` neither CV1 nor CV2 can run; the report prints an info
row for each instead of implying that every citation resolves.

Symbol extraction is narrower than `claim_lint`'s test-ID index:

| Shape | Pattern |
| --- | --- |
| Python `report("F3a ...")` | an ID matching `[A-Z]{1,5}\d+[a-z]?` |
| Python `def test_*` | `\bdef\s+(test_[A-Za-z0-9_]+)` |
| Rust test | `#[test] fn name` (optional `pub` / `async`) |

The first pattern is narrow on purpose. `claim_lint` accepts any first word of
a report label, so `report("DELETE FROM ...")` yields a fake ID; the coverage
report only counts identifiers that look like test IDs. Symbols produced by
other conventions (Go `func TestX`, JS `it(...)`, table-driven cases, helper
functions) are invisible, and the report does not say so per file.

Mapping is **file-level**: a symbol counts as mapped when its file is a
detector artifact, or when the same symbol is cited by a claim or a negative
test. This shows which suite files nobody mapped. It does **not** show whether
a detector executes every test in a mapped file, whether the named test is the
one that proves the cell, or whether the test passes.

`stale` uses `last_verified` when present, otherwise the newest dated evidence
item. A non-open claim with no usable date is reported as `no date` and counts
as stale: freshness that cannot be shown is not freshness.

`open` claims and cells are excluded from CV3 and CV4 by design; open work has
not claimed coverage yet. CV1 still checks citations from open detectors,
because a citation that resolves nowhere is wrong regardless of status.

## Recorded measurement (2026-11-07)

The two JSON snapshots are written by `make coverage-record`; the printed
report is part of `make verify`.

| Pilot | Cells | Symbols | Mapped | Unmapped | Stale | No fixture | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rbac_pg` | 29 (26 non-open) | 80 | 67 | 13 | 0 of 6 | 0 (3 exemptions) | 0 |
| `craft-i18n` | 14 (13 non-open) | 26 | 26 | 0 | 0 of 7 | 0 (1 exemption) | 0 |

The 13 unmapped symbols are real, not noise: `setup/test_4_lvl.py` (5) and
`setup/test_negative.py` (8) are suite files no artifact cites and no claim
cites. 18 of 28 `rbac_pg` suite files are uncited; only these two contain
recognised symbols, so the count is small while the file-level gap is wider.
80 is the number of (file, symbol) sites, not unique names: the ID `M1` exists
in `setup/test_fstek.py` and `setup/test_v191_fixes.py`, so it is counted twice.
`craft-i18n` has 26 of 26 mapped because its registry was authored against the
test names.

Artifacts:

- `2026-11-07-rbac-pg.json`
- `2026-11-07-craft-i18n.json`

## Thresholds

All three thresholds are optional. Without them the report is a measurement,
not a gate, and `make verify` fails only on CV1. This is deliberate: a
threshold picked before the number is observed would be a guess, and the
recorded numbers above are the basis for choosing one later. To turn a number
into a gate:

```bash
python3 tools/coverage_report.py \
  --cells spec/pilots/rbac_pg/cells.yaml --root ../rbac_pg \
  --suite-glob "setup/*.py" --ledger ../rbac_pg/docs/claims.yaml \
  --max-unmapped 13 --max-stale-claims 0 --max-cells-without-fixture 0
```

## Negative controls

- `evals/coverage/` — 14 cases: clean control; unmapped info and threshold;
  dangling claim test and dangling negative test; stale info, threshold and
  missing date; fixture threshold, exemption, non-test detector; open work
  excluded; no suite glob; missing root. All pass.
- The clean control asserts thresholds pass at 0, so an always-failing report
  would not pass the suite.
- Injecting `NO_SUCH_9` into a copy of the `craft-i18n` ledger in `/tmp` makes
  CV1 error (`cited symbol 'NO_SUCH_9' from C-01 is not in the suite`) and exit
  1; the repository ledger is not modified.
- `--max-unmapped 0` on the real `rbac_pg` pilot fails with
  `unmapped symbols 13 exceed --max-unmapped 0`, so the measured number can be
  turned into a gate without editing the tool.

## Limits

- File-level mapping is coarse; it is not test-level coverage.
- The three symbol patterns are a scanner, not an AST. A test function defined
  through a macro or generated at build time is invisible.
- `no date` is treated as stale; a ledger whose dates are all in the future is
  not flagged.
- A threshold is a policy, not a proof that the remaining mapped symbols are
  the right ones.
- The report reads the working tree, not a recorded target commit. The JSON
  snapshots pin the date, root and suite glob, but not the target's commit; a
  target checkout that moves between runs changes the numbers.
