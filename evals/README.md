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
  fuzz/
    run_evals.py        # fuzz_run.py: oracle, budget, determinism
    cases/
  fuzz-triage/
    run_evals.py        # fuzz_triage.py: completeness, routing, agreement
    cases/
  coverage/
    run_evals.py        # coverage_report.py: CV1-CV4 fail closed
    cases/
  diff-coverage/
    run_evals.py        # diff_coverage.py: DC1-DC5 fail closed on a git range
    cases/
  choke-points/
    run_evals.py        # choke_points.py: CP1-CP2, spans and classification
    cases/
  mutation-plan/
    run_evals.py        # mutation_plan.py: diff -> cells -> fixtures (V2-11)
  invariant-catalog/
    run_evals.py        # invariant_catalog.py: INV1-INV5 fail closed (V2-21)
  sarif/
    run_evals.py        # sarif_evidence.py: mapping, unmapped, provenance (V2-23)
  bounded-check/
    run_evals.py        # bounded_check.py: timeout -> unverified, group kill (V2-28)
  proof-plan/
    run_evals.py        # proof_plan.py: diff -> proofs to re-run (V2-29)
    mutation_selftest.py  # 8 mutants; each must turn a named case red
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
`evals/linter/` runs 40 cases, including 8 `run-record-*` cases (valid record,
artifact hash, log hash, unexecuted test, non-zero exit, missing record, date
mismatch, count mismatch), two V2-09 controls — `unrelated-commit` and
`empty-claims` — three V2-05 tombstone cases, seven V2-10 `tool-output-*`
cases (valid record, hash mismatch, missing output, non-zero exit, date
mismatch, no `tool_output` for a model-checked claim, no bound), and five
V2-28 cases (`status: unverified` with exit 0, a wall-clock timeout with a
truncated log, `timed_out` contradicting `status`, a record with no `status`,
and an open claim that honestly keeps an `unverified` record); `evals/cell-lint/`
runs 40 cases, including the `other` + `routing_note` escape hatch, four V2-05
cases (removal without a tombstone, removal with one, a dropped tombstone, a
tombstone with no reason) and six V2-15/V2-16 cases (a valid runtime-enforcement
cell, missing `enforced_at`/`oracle`/`violation_response`, no `negative_test`, an
unresolved negative test, an unchecked one without `--suite-glob`, and a status
overclaim). The status-diff evals cover fail-closed base handling
and 13 scenarios in total, five of them for V2-05. `evals/fuzz/` runs 5 cases
for `tools/fuzz_run.py`: a failing seed (one finding, source named), a clean
target whose two identical runs must produce the same `executions_digest`, a
traceback oracle that fires on exit 1 (the oracle is not hard-wired to exit
codes), `max_findings` stopping the run and saying so, and a missing corpus
exiting 2 with no record. `evals/fuzz-triage/` runs 13 cases for
`tools/fuzz_triage.py`: a clean record with an empty triage (control), a valid
`covered` entry, an untriaged finding, a triage naming the wrong record, a
dismissal without a reason, a duplicate entry, a stale entry, a cell outside the
registry, a detector outside its cell, a fixture ID absent from the mutations
file, a `new` entry without a fixture, a named cell with no registry, and a
record whose verdict contradicts its findings. `evals/coverage/` runs 14 cases
for `tools/coverage_report.py`: a clean control that passes every threshold at
zero, unmapped symbols at info and above a threshold, a dangling claim test, a
dangling negative test, a stale claim at info, above a threshold, and with no
usable date, a missing fixture above a threshold, an exempted detector, a
non-test detector that owes no fixture, open work excluded from both checks, a
run without `--suite-glob`, and a missing root returning a usage error.
`evals/diff-coverage/` runs 19 cases for `tools/diff_coverage.py`, each built
from a synthetic git repository: a clean path and symbol, an unmapped path, an
unmapped symbol, a symbol mapped only by a test ID, an untouched choke point
(DC4), a missing declaration path, a prose declaration, an open claim that does
not count, a deleted file, an added SQL symbol, a registry with no declarations
(DC5), a threshold that tolerates one unmapped entity, a renamed file, a
missing ref returning 2, a SQL body-only edit, a Rust block-comment brace, a
Python decorator-only change, a comment-only symbol mention that the masked
fallback must ignore, and a head file whose definitions shift down so the base
blob is not read with head line numbers. `evals/choke-points/` runs 14 cases for
`tools/choke_points.py`: Python decorator spans and a docstring `def`, a syntax
error counted with CP2 red, Rust comments/raw strings/char literals, SQL
dollar-quoted bodies with internal semicolons, SQL definitions inside comments,
rule precedence, unclassified reported with CP1 red at zero, the same candidate
green at a threshold of one, `taxonomy_class: other` rejected, unknown taxonomy
and failure-mode enums rejected, unknown extensions skipped, and a missing root
or rules file returning 2. `evals/mutation-plan/` runs 13 cases for
`tools/mutation_plan.py` on synthetic git repositories: no selection on an
unrelated diff, selection by fixture artifact, `enforced_at` path, detector
artifact and changed registry, a changed non-open cell without a fixture failing
`--require-fixtures`, an exemption and an open cell not failing, `--all`,
deleted artifacts, an unknown base and a missing fixtures file. `evals/invariant-catalog/`
runs 15 cases for `tools/invariant_catalog.py`: the five categories and their
minimum size, ID prefixes, unknown cells and rules, `other` classes, one-bypass
entries, referenced/out-of-scope overlap, an unmapped seed cell, a non-open
entry without an evidence path, and a missing catalogue returning 2.
`evals/sarif/` runs 15 cases for `tools/sarif_evidence.py`: three engines mapped,
duplicate fingerprints, unknown engine, unmapped rule, missing location and rule
ID, a bad SARIF version and invalid JSON, `--require-engines`,
`--reject-fixtures`, an unknown cell and an `other` class as config errors, a
`file://` URI rebased to the root, and a digest that is stable when input order
changes. `evals/bounded-check/` runs 10 cases for `tools/bounded_check.py` on
real child processes: a clean control whose log keeps stdout/stderr arrival
order and whose SHA-256 is recorded, a timeout recorded as `unverified` with
`timed_out: true` and a negative exit code, a non-zero exit recorded as
`failed`, a missing binary recorded as `error` with exit 127, `--timeout 0`
and an empty command rejected with exit 2 and no record, a record written to
`--json` with stdout left clean, a grandchild process that must not survive the
process-group kill, and two integration cases where `claim_lint` accepts a
`completed` record and rejects an `unverified` one for a `model-checked` claim.
Reproduce all thirteen:

```bash
python3 evals/linter/run_evals.py
python3 evals/cell-lint/run_evals.py
python3 evals/status-diff/run_evals.py
python3 evals/fuzz/run_evals.py
python3 evals/fuzz-triage/run_evals.py
python3 evals/coverage/run_evals.py
python3 evals/diff-coverage/run_evals.py
python3 evals/choke-points/run_evals.py
python3 evals/mutation-plan/run_evals.py
python3 evals/invariant-catalog/run_evals.py
python3 evals/sarif/run_evals.py
python3 evals/bounded-check/run_evals.py
python3 evals/proof-plan/run_evals.py
```

`evals/proof-plan/` (V2-29) builds a throw-away git repository per case, writes
a manifest and a `tool_output` record, and checks the plan: which proof is
`rerun` and why, which is `fresh` because its record postdates the last change,
what a rename or a delete does, and that both gates exit 1 while a broken
manifest exits 2. 36 cases. The suite is only evidence if it can fail, so
`evals/proof-plan/mutation_selftest.py` applies eight named mutations to
`tools/proof_plan.py` and requires the case named for each behaviour to go red;
it runs ~80 s and is a separate target (`make proof-plan-selftest`), not part of
`make verify`.

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

The fuzz cases exercise the adapter, not a real target: a passing run says the
oracle, budget and determinism rules hold, not that any program is bug-free.
The triage cases exercise the gate on synthetic records, because the committed
run has no findings; they show it fails closed, not that a real finding was
routed correctly. The coverage cases exercise the report on synthetic suites;
the clean control passes every threshold at zero, so an always-red report
cannot pass the suite, but a green case says nothing about a real target's
coverage. The diff-coverage cases exercise the gate on synthetic git
repositories; they show that DC1–DC5 fail closed on the named defects, not that
a real PR range maps every changed choke point. The choke-point cases exercise
the extractor and the rule gate on synthetic trees; they show spans and
classification fail closed on the named forms, not that a real codebase has a
particular unclassified share. The bounded-check cases exercise the supervisor
on `python -c` children; they show that it classifies its own child faithfully
and that the linter refuses `unverified` for a non-open claim, not that a real
model checker is bounded correctly or that a child cannot escape the group by
double-forking.

## Reproduce

Run each prompt with the relevant `SKILL.md` loaded, save the answer under
`with_skill/outputs/`, then run the same prompt without reading the skill and
save under `without_skill/outputs/`. Compare against the assertions in
`evals.json`. Keep the outputs; do not overwrite an iteration.
