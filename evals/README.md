# Skill Evaluations

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

## Reproduce

Run each prompt with the relevant `SKILL.md` loaded, save the answer under
`with_skill/outputs/`, then run the same prompt without reading the skill and
save under `without_skill/outputs/`. Compare against the assertions in
`evals.json`. Keep the outputs; do not overwrite an iteration.
