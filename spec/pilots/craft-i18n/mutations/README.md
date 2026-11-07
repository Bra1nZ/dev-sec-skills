# Mutation fixtures — craft-i18n pilot

These fixtures answer the question the cell registry cannot answer on its own:

> **Can each detector fail at all?**

Each fixture mutates exactly one enforcement artifact in a throw-away copy of
`craft-i18n`, runs the checker suite that is supposed to catch the regression,
and requires the suite to fail **exactly** on the predicted tests. The target
repository is never modified.

## What a passing fixture proves

- The detector executes and produces a pass/fail verdict in this environment.
- The named assertion is coupled to the mutated mechanism: break the
  mechanism and the assertion flips.
- The rest of the suite still passes, except for failures that are predicted
  in `expect_failures`; the mutation is not a blunt instrument that breaks
  everything.

## What it does not prove

- It does not prove the detector is complete. It fails for **this** mutation;
  other bypasses of the same property may still pass. The app-file-name gap
  below is a concrete example of a mutation that stayed green.
- It does not prove the property holds in production. A mutation fixture is a
  sensitivity check, not a proof of correctness.
- The fixture exercises the checker's rules, not the apps' rendering, CLDR
  agreement, or the translators' work.

## Method

1. Preflight: every artifact must match the sha256 pinned in
   [`mutations.yaml`](mutations.yaml), so a fixture cannot silently run against
   a different revision.
2. An unmutated copy runs first; the baseline must exit 0 with no failures.
3. For each fixture: copy the target, apply the anchor replacement (each anchor
   must occur exactly once), rebuild, run the suite.
4. Parse the failing test names, strip Rust module prefixes
   (`catalog::tests::foo` → `foo`), and compare the set with `expect_failures`
   **exactly** — extra failures fail the fixture too.

The suite runs as `cargo test --offline --no-fail-fast -p craft-i18n-tests`.
`--no-fail-fast` matters: without it cargo stops after the first failing test
target, so the second target's failures would be invisible and the expected
sets would be wrong for the wrong reason.

## Results (2026-11-06)

Target commit `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256`. Unmutated baseline:
**26 tests, 0 failed** (9 lib + 17 integration).

| Fixture | Cell | Detector | Mutation | Failing tests observed |
|---|---|---|---|---|
| MUT-001 | CELL-001 | D-CLEANROOM | clean-room header check always passes | `missing_clean_room_rule` |
| MUT-002 | CELL-003 | D-ROWS | empty translation accepted | `each_bad_row_is_one_problem` |
| MUT-003 | CELL-004 | D-PLACEHOLDERS | `placeholders()` returns an empty list | `each_bad_row_is_one_problem` |
| MUT-004 | CELL-005 | D-ESCAPES | unknown escape pushed as a literal character | `each_bad_row_is_one_problem` |
| MUT-005 | CELL-006 | D-UNIQUE | duplicate-key insert made unconditional | `each_bad_row_is_one_problem` |
| MUT-006 | CELL-007 | D-PLURALS | plural form count check dropped | `plural_count_by_locale`, `each_bad_row_is_one_problem` |
| MUT-007 | CELL-008 | D-MSG | `check_template()` returns `Ok` for every template | `msg_templates_one_good_two_bad`, `each_bad_row_is_one_problem` |
| MUT-008 | CELL-009 | D-OVERRIDE | override comparison disabled | `redundant_override` |
| MUT-009 | CELL-010 | D-REGIONAL | regional redundancy checked for every locale | `script_and_baseless_locales_have_no_regional_check`, `repository_catalogs_pass` |
| MUT-010 | CELL-011 | D-LANGNAME | `has_language_name()` always true | `missing_language_name` |
| MUT-011 | CELL-012 | D-NAMING | lowercase equality relaxed to case-insensitive | `locale_names` |
| MUT-012 | CELL-014 | D-COVERAGE | coverage row count forced to 0 | `coverage_counts_rows_against_largest_locale` |

`fixtures: 12/12 matched`. CELL-013 carries a documented `mutation_exemption`:
it is a data-level check on the target's own `locales/`, and every source
mutation that makes the repository catalogs fail also fails the rule tests the
same suite runs.

### Why some fixtures fail more than one test

`catalog::tests::each_bad_row_is_one_problem` bundles twenty malformed rows in
one test. MUT-003…MUT-007 each remove one row rule, so this catch-all test
fails alongside the test named for the cell. The expected sets include it
explicitly rather than filtering it out: an unexpected extra failure is
treated as a fixture failure.

MUT-009 removes the "only a region subtag falls back" condition, so the
repository's own script-variant locales are compared against their base
catalogs and `repository_catalogs_pass` fails too. That is the mutation doing
what it says, not collateral noise.

## Negative result: the app-file-name rule is not pinned

The first draft of MUT-011 targeted the catalog file-name rule instead of the
locale-name rule:

```text
tree.rs: .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
      →  .all(|b| b.is_ascii_alphanumeric())
```

The whole suite stayed green: **26 passed, 0 failed**. The rule that rejects an
uppercase letter in an app catalog file name is enforced by the source, but
`bad_app_file_name` only exercises `Word_Craft.tsv`, whose underscore is
rejected by both the original and the mutated predicate. The shipped MUT-011
therefore targets `locale.rs`, whose `locale_names` test does pin the lowercase
rule. The untested branch is recorded as a limitation of C-06 and CELL-012, not
hidden by a fixture that happens to pass.

## Harness note: shared target dir and mtimes

The runner shares one `CARGO_TARGET_DIR` across fixtures to avoid rebuilding
dependencies twelve times. `shutil.copytree` preserves mtimes by default; a
copy of the original source then looks *older* than the fingerprint left by the
previous fixture's mutated build, and cargo reuses the stale artifact. The
first run of this batch failed its baseline for exactly that reason
(`coverage_counts_rows_against_largest_locale` failed on unmutated code).

The runner now copies with `copy_function=shutil.copy`, which stamps fresh
mtimes and forces a rebuild from each copy. The baseline check makes this
failure loud instead of letting a fixture "pass" against the wrong binary.

## Reproduction

```bash
python3 spec/pilots/craft-i18n/mutations/run_mutations.py \
    --target /home/admini/projects/astraoffice/craft-i18n
```

Logs are written to `/tmp/opencode/craft-i18n-mutations/results/`; the target
repository is only read.

`--only MUT-003`, `--only-cell CELL-004` and `--plan plan.json` select a
subset. `--plan` consumes the JSON written by `tools/mutation_plan.py`; an
empty plan runs nothing and exits 0, so CI can skip the build when a diff
touches no fixture, cell, choke point or detector artifact.
