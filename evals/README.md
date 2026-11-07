# Skill Evaluations

Run every suite with `make verify` (add `make mutations` for the mutation
suites, which need a live stand). Each suite exits non-zero on a failing case;
the status-diff suite reports one recorded known gap and still exits 0.

These are direct application tests, not trigger-rate tests. Each prompt was
given to an independent agent with the skill loaded (`with_skill`) and to
another agent without the skill (`without_skill`). The point is to check
whether the skill changes the answer in the intended direction, not to measure
how often the description auto-triggers.

## Layout

```text
evals/
  evals.json
  iteration-1/
    <eval-name>/
      with_skill/outputs/answer.md
      without_skill/outputs/answer.md
    RESULTS.md
  iteration-2/
    <near-miss-name>/
      with_skill/outputs/answer.md
      without_skill/outputs/answer.md
    evals.json
    RESULTS.md
  iteration-3/
    RESULTS.md          # claim_lint: 12 adversarial cases
  iteration-4/
    RESULTS.md          # cell_lint: 26 adversarial cases
  linter/
    run_evals.py
    cases/
  cell-lint/
    run_evals.py
    cases/
  status-diff/
    run_evals.py        # fail-closed base handling; one recorded known gap
```

## Prompts

Iteration 1 has six realistic tasks. Iteration 2 adds three near-miss tasks
where a confident review can rest on a weak guard or stale evidence.

- `negative-test-first`: money-transfer concurrency/boundary gaps; RLS
  `invoices` update-policy review.
- `evidence-first-docs`: rewrite an overclaiming README; draft release notes
  with stale and missing evidence.
- `invariant-first-code`: review a handler-only tenant check with a batch
  bypass; design invariants for a multi-tenant invoice API.

Iteration 2 near-misses:

- `docs-near-miss-release`: a migration described as backward-compatible and
  safe, with stale sanitizer evidence and an unexercised rollback.
- `ntf-weak-negative`: three green negative tests with a deny-only permission
  mock and status-code-only assertions.
- `code-platform-masks`: RLS enabled, but the production role owns the table
  with `BYPASSRLS` and a `SECURITY DEFINER` function trusts a tenant header.

## Scoring

`RESULTS.md` records assertion pass/fail by inspection. The assertions are in
`evals.json`. This is a qualitative evaluation; a keyword script cannot judge
whether a claim ledger is honest or whether a test can actually fail.

## Executable linters

Iteration 3 covers `tools/claim_lint.py`; iteration 4 covers
`tools/cell_lint.py`. The live suites have grown beyond those iterations:
`evals/linter/` runs 35 cases, including 8 `run-record-*` cases (valid record,
artifact hash, log hash, unexecuted test, non-zero exit, missing record, date
mismatch, count mismatch), two V2-09 controls — `unrelated-commit` and
`empty-claims` — three V2-05 tombstone cases, and seven V2-10 `tool-output-*`
cases (valid record, hash mismatch, missing output, non-zero exit, date
mismatch, no `tool_output` for a model-checked claim, no bound); `evals/cell-lint/`
runs 34 cases, including the `other` + `routing_note` escape hatch and four V2-05
cases (removal without a tombstone, removal with one, a dropped tombstone, a
tombstone with no reason). The status-diff evals cover fail-closed base handling
and 13 scenarios in total, five of them for V2-05. Reproduce all three:

```bash
python3 evals/linter/run_evals.py
python3 evals/cell-lint/run_evals.py
python3 evals/status-diff/run_evals.py
```

A case may declare `git.commits`; the runner commits them in order and
substitutes each resulting SHA as `{{COMMIT_<n>}}` into later commit files, the
fixture files and the ledger. That is how `unrelated-commit` cites a commit that
resolves while the artifact's bytes have moved on — a plain fixture without
`.git` cannot express the failure.

All runners need PyYAML. A passing run means the contract holds on synthetic
adversarial fixtures, not that a production ledger or registry is clean.
`status-diff` prints `GAP` for the re-dating scenario while that hole remains
open: the tool compares evidence identities and cannot tell a genuinely new run
from a re-dated one. A `run_record` lets `claim_lint` L2 catch re-dating in the
ledger, but without an external anchor (C-13) a consistent forgery of the record
and the log still passes.

## Reproduce

Run each prompt with the relevant `SKILL.md` loaded, save the answer under
`with_skill/outputs/`, then run the same prompt without reading the skill and
save under `without_skill/outputs/`. Compare against the assertions in
`evals.json`. Keep the outputs; do not overwrite an iteration.
