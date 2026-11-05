# Iteration 3 — linter evals (claim_lint.py)

Date: 2026-11-05. Scope: `tools/claim_lint.py` (checks L1–L5) against a
synthetic adversarial suite. Status: **12/12 cases pass** (run shown below).

## Method

Each case in [`evals/linter/cases/`](../linter/cases/) is a synthetic project
(fixture files + inline ledger) with expectations: for each check L1–L5 either
a severity that must appear (`error` / `warning` / `info`) or `none`, plus the
expected exit code. `evals/linter/run_evals.py` materializes each fixture in a
temp directory, runs `claim_lint`, and compares parsed `[Lx] severity` lines
against the expectations.

Fixtures are synthetic and marked as such in every file. A passing run means
the linter's contract holds on the adversarial cases; it is **not** evidence
that any production ledger is clean.

## Cases

| Case | Adversarial move | Expected |
| --- | --- | --- |
| `fake-test-id` | status=tested cites report ID absent from the suite | L3 error + L4 error |
| `stale-evidence` | evidence 2025-01-01, beyond the 90-day window | L2 warning |
| `tested-without-test-evidence` | status=tested, only kind=review evidence | L4 error |
| `open-without-limitations` | status=open, no `limitations` | L1 error |
| `duplicate-ids` | two claims share C-01 | L1 error |
| `unknown-status` | status `verified` outside the enum | L1 error |
| `missing-artifact` | artifact path does not exist | L2 error |
| `bad-commit` | commit hash does not resolve | L2 error |
| `bad-id-format` | ID `C-1` outside `^C-[0-9]{2,}$` | L1 error |
| `proof-below-status` | proof evidence present, status=tested | L4 warning |
| `future-date` | evidence dated 2099-01-01 | L2 warning |
| `valid-clean` | control: well-formed ledger, no findings, exit 0 | all checks none |

## Result

```
PASS bad-commit ... PASS valid-clean
evals: 12/12 passed
```

## Negative controls

1. **Runner self-check.** A case with a deliberately wrong expectation
   (`valid-clean` expecting L3=error) fails as `0/1 passed` with exit 1 — the
   runner does not pass vacuously.
2. **Context filter (item а).** Synthetic prose lines: a self-claim
   ("Модуль гарантирует...") stays a warning; third-party lines
   ("Гарантирует платформа", "Это гарантирует платформа ЗСУБД") are downgraded
   to info. See `styles/README.md`.

## Harness notes (recorded findings)

1. **Commit check fails closed outside a repository.** `L2` runs
   `git cat-file -e <commit>^{commit}` with the fixture root as cwd; a temp
   directory without `.git` makes every commit unresolvable. The `bad-commit`
   case therefore verifies the error path, not repository resolution itself.
2. **Freshness fixtures are date-anchored.** `valid-clean` uses
   `--max-age-days 3650` to stay evergreen; freshness is covered by
   `stale-evidence` and `future-date` instead.
3. **L5 info findings are counted but not rendered** by `claim_lint`; the
   runner matches on rendered `[Lx] severity` lines, so L5 expectations are
   limited to warnings/errors. Sufficient for the current cases; revisit if
   info-level L5 cases are added.

## Re-run

```
cd dev-sec-skills && python3 evals/linter/run_evals.py
```
