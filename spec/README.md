# Specs

Design artifacts for the verification conveyor. This directory is the
knowledge layer of the system; pipeline code lives elsewhere, and the cell
linter is the executable exception.

## Files

```text
spec/
  conveyor/
    CONCEPT.md                    # living concept, Russian source of truth
    CONCEPT.en.md                 # English derivative
    cell-registry.schema.json     # JSON Schema (draft-07) for the cell registry
    cells.seed.yaml               # seed cells from the six invariant categories
    guard-grammar.md              # bounded guard grammar for L2, Russian source
    guard-grammar.en.md           # English derivative
    product-trials.md             # product-trial boundary: criteria, metrics (draft)
    product-trials.en.md          # English derivative
  pilots/
    rbac_pg/
      cells.yaml                  # 29 cells derived from rbac_pg detectors
      README.md                   # calibration, findings, limits
      mutations/
        mutations.yaml            # 25 mutation fixtures, pinned by sha256
        run_mutations.py          # verifies each detector fails as predicted
        README.md                 # what a fixture proves, results, gaps
    craft-i18n/
      cells.yaml                  # 14 cells: a Rust catalog checker, no DB
      claims.yaml                 # 8 claims, authored here; target untouched
      README.md                   # second-pilot calibration and limits
      mutations/
        mutations.yaml            # 12 fixtures, pinned by sha256
        run_mutations.py          # Rust-aware runner, exact failing-set match
        README.md                 # results, a negative result, harness notes
      probes/
        invisible-characters/     # C-08 evidence: Cf chars pass the checker
  fuzz/
    README.md                     # what a fuzz record proves, oracle rules
    corpus/claim-lint/            # five seed ledgers
    runs/claim-lint-2026-11-07.json  # recorded run: 155 executions, clean
    triage/claim-lint-2026-11-07.yaml  # V2-18 triage: no findings, no entries
  coverage/
    README.md                     # CV1-CV4: method, measured numbers, limits
    2026-11-07-rbac-pg.json       # recorded coverage snapshot
    2026-11-07-craft-i18n.json    # recorded coverage snapshot
  diff-coverage/
    README.md                     # DC1-DC5: declarations, extractor, measured numbers, limits
    2026-11-07-rbac-pg.json       # recorded diff-coverage snapshot
    2026-11-07-craft-i18n.json    # recorded diff-coverage snapshot
  choke-points/
    README.md                     # CP1-CP2: signals, rules, extractor, measured numbers, limits
    rules.yaml                    # signals and ordered class-mapping rules
    2026-11-07-rbac-pg.json       # recorded choke-point scan snapshot
    2026-11-07-craft-i18n.json    # recorded choke-point scan snapshot
  invariants/
    README.md                     # INV1-INV5: method, categories, measured coverage, limits
    catalog.yaml                  # 5 general-code categories, 15 invariants, out_of_scope cells
    2026-11-07-coverage.json      # recorded catalogue coverage snapshot
  sarif/
    README.md                     # engine/rule -> taxonomy mapping, fixture provenance, limits
    adapters.yaml                 # 3 engines, ordered rules, registry aliases
    fixtures/                     # authored SARIF: semgrep, codeql, bandit
    2026-11-07-report.json        # recorded normalized report
  proofs/
    README.md                     # re-run triggers, freshness, P-01/P-02, limits
    manifest.yaml                 # P-01/P-02: the bounded C-02 cross-check
    c02-bound-2026-11-07.md       # declared bound, space and decision rule
    runs/
      c02-crosscheck-2026-11-07.json  # P-01 tool_output record
      c02-crosscheck-2026-11-07.log   # captured stdout, hash-checked
      c02-mutants-2026-11-07.json     # P-02 tool_output record
      c02-mutants-2026-11-07.log      # captured stdout, hash-checked
  red-team/
    README.md                     # 14 attacks on the real pilot artifacts, 1 recorded gap
    run_drills.py                 # one mutation per drill, real tool, expected message
    2026-11-07-drills.json        # recorded result: 13 blocked, 1 allowed
```

Changed-cell selection (V2-11) lives in `tools/mutation_plan.py`, not under
`spec/`: it reads a registry, a mutations file and a target diff, prints the
selected fixtures and writes a JSON plan. Both pilots' runners accept
`--plan`; an empty plan runs nothing and exits 0. `make mutation-plan` writes
`/tmp/opencode/mutation-plan-{rbac,i18n}.json`. The template
`ci/mutation-changed.yml` resolves the PR merge base, fails a changed cell with
no fixture and no exemption (`--require-fixtures`), and skips the expensive
stand when the plan is empty. The template has not been exercised on a real
runner; the selector has 13 synthetic eval cases in `evals/mutation-plan/`.

## Status

Phase 0: documents, schemas, seed registry, `cell_lint` (CL1–CL6, 40
synthetic adversarial cases, see `evals/cell-lint/`), and two pilot registries.
The first is `rbac_pg` (29 cells, 26 non-open, 3 open, 0 CL1/CL3/CL4 errors,
C-18); the second is `craft-i18n`, deliberately non-RBAC and non-database
(14 cells, 13 non-open, 1 open, 0 errors, 1 exemption). All static gates run
with `make verify` (V2-08): the evals, the seed registry, both pilot registries
with their claim ledgers, the ledgers themselves, and the status diffs.

24 of the first pilot's 27 detectors are mutation-verified: each named suite
fails exactly on the predicted tests when its mechanism is removed; the other
three carry a documented `mutation_exemption` because no repository-level
mutation can flip them. In the second pilot, 12 of 13 detectors have a fixture
and one carries an exemption; all 12 matched on 2026-11-06. Mutation runs are
separate: `make mutations` needs a live PostgreSQL stand, `make mutations-i18n`
needs cargo; `make mutations-all` runs both. There is no production registry and
no claim that the conveyor exists. Every material statement in `CONCEPT.md`
carries a status from the evidence-first ladder; design intents are `open` and
carry limitations.

Run-record evidence (V2-01/V2-02) is part of the contract: `claim_lint` L1
checks the record's shape and commit/command agreement, L2 recomputes the log
and artifact SHA-256, matches the run date to the evidence date, and requires
every cited test ID in the log. The seven `craft-i18n` test claims carry one
(`pilots/craft-i18n/runs/`); the `rbac_pg` ledger has none and gets 6 visible
L2 warnings.

Tool output (V2-10) closes the model-checked/proven gap: an artifact proves that
a model exists, not that a checker ran over it. `evidence[].tool_output` names
the tool and its command, the captured output and its SHA-256, the exit code,
the run status and the bound; `claim_lint` L1 checks the shape, L2 recomputes
the output hash, ties `finished_at` to the evidence date and rejects a non-zero
exit for a non-open claim, and L4 rejects a `model-checked` or `proven` claim
without one. A `model-checked` claim must also state its bound. The record does
not check the tool's semantics or the soundness of the encoding.

Bounded fallback (V2-28) makes that record say how the run ended, because a
killed checker and a finished checker can leave the same artifact. `status` is
required and is one of `completed`, `unverified`, `failed` or `error`;
`tools/bounded_check.py` starts the command in its own process group, kills the
group at `--timeout`, and writes the combined log with its SHA-256. A timeout
is `unverified` with `timed_out: true` and a negative exit code; L1 rejects a
`timed_out` flag that contradicts the status, and L2 rejects any `status` other
than `completed` for a non-open claim. An open claim may honestly keep an
`unverified` record. The rules are in `conveyor/guard-grammar.md` §6.6; the
supervisor has 10 eval cases in `evals/bounded-check/`, including a grandchild
process that must not survive the group kill and two `claim_lint` integration
cases. The supervisor classifies its own child; it does not prove a real
checker's semantics, and a child that double-forks out of the group can still
escape the kill.

Runtime enforcement (V2-15/V2-16) is a separate evidence kind: a detector with
`kind: runtime-enforcement` must name the `negative_test` that attempts the
forbidden action and observes the response, and its cell must name
`enforced_at` (the choke point), `oracle` (what decides a violation occurred)
and `violation_response` (what the system does). CL1 checks the shape, CL3
resolves the test ID against `--suite-glob`, and CL2 caps such a cell at
`tested`: execution against examples is not a proof. The first adopters are
`rbac_pg` CELL-001 (a role-less login gets PostgreSQL 42501, negative test F3a)
and `craft-i18n` CELL-003 (`parse_row` returns `line N: ...`, negative test
`each_bad_row_is_one_problem`); `make verify` passes the suite glob for both, so
the IDs resolve rather than being assumed.

Fuzzing (V2-17) has a record instead of a session: `tools/fuzz_run.py` runs a
target over a seed corpus and random mutations with a fixed seed, checks every
execution against explicit oracle rules, and writes
`schemas/fuzz-run.schema.json`. The committed run is `fuzz/runs/claim-lint-2026-11-07.json`
(5 seeds, 150 mutated runs, 155 executions, seed 20261107, verdict clean);
`executions_digest` is the SHA-256 of the ordered input hashes, and
`make fuzz-claim-lint` replays the run and compares it. The adapter is not
coverage-guided, and a clean verdict is scoped to that oracle and budget, not a
statement that the target is free of bugs.

The first CI in this repository (V2-19) is that replay on a timer:
`.github/workflows/fuzz-nightly.yml` runs on cron and on manual dispatch, never
on `push`/`pull_request`, so it cannot block a merge. It fails when
`executions_digest` moves and uploads a `fuzz-record-<run_id>` artifact for 90
days. The first dispatch (run 42394278295, 2026-11-07) succeeded with digest
`93e1af3183658aa6…`, seed 20261107, 155 executions and 0 findings; the
downloaded artifact was compared with the committed record. The difference
from `ci/` is scope: `ci/` holds templates for *target* repositories, while
`.github/workflows/` runs on this repository. The replay proves determinism and
input integrity, not new-bug discovery, and the nightly schedule itself had not
fired at the time of writing.

Event-driven `proven` (V2-29) is `tools/proof_plan.py` plus
`spec/proofs/manifest.yaml`: each proof declares the code, model, encoding and
tooling it depends on, and a diff decides which proofs must be re-run. The
manifest declares two bounded checks, P-01 (agreement) and P-02 (mutation
control), for the `tested` claims C-38/C-39; they are not `proven` claims,
because agreement inside a declared vocabulary is not a proof of the universal
statement. `make proof-plan` resolves the merge base of `origin/main..HEAD` and
prints the plan; on `a3293ec..4f3e25c` it reports 2 fresh / 0 rerun, and the
docs-only `02be7ab~1..02be7ab` also reports 0 rerun. The planner is covered by
36 synthetic git cases in `evals/proof-plan/` and by eight mutants of itself
(`make proof-plan-selftest`, not in `verify`). It does not verify the record
hash (`claim_lint` does), does not check that the model matches the code, and
decides freshness from timestamps, so a record produced from a stale checkout
still looks fresh. The target checkout is outside this repository, so a change
to it after the pinned commit is not a diff here; the pin is declared and
`claim_lint` L2 compares the cited artifact with its blob at the cited commit.

Gate strength is measured against the real artifacts, not only fixtures (C-35):
`spec/red-team/run_drills.py` takes the committed craft-i18n ledger, its cargo
log and the cell registry, applies one attack per drill, and requires the exit
code and the expected message. Twelve of thirteen attacks are blocked; the
record is `spec/red-team/2026-11-07-drills.json`. One stays green and is
recorded as a gap: re-dating a run (identity includes the date, so a shifted
date is "new evidence", the C-13 hole). Borrowing another claim's real tests is
now blocked by L6 (V2-34): a shared test must be declared with a reason, and a
non-open claim must keep at least one test of its own, so declaring the sharing
does not reopen the gap. An `allowed` drill fails the harness if a future gate
starts blocking it, so the recorded gap cannot become stale silently. The
drills need the craft-i18n checkout and are not in `make verify`; they run
`claim_lint --no-vale`, so L5 is not exercised there.

Every finding must become a cell, a detector and a fixture (V2-18):
`tools/fuzz_triage.py` checks one entry per finding, resolves the cell and
detector in the registry the triage names, checks the fixture ID in the
mutations file, and rejects a stale entry or a verdict that disagrees with the
findings. The committed triage is empty because the run is clean; that is the
only case an empty triage is accepted, and a finding injected into a copy of the
record makes the gate exit 1. The gate proves the artifacts exist, not that the
routing call was right.

Coverage is measured, not assumed (V2-20): `tools/coverage_report.py` reports
cited symbols that resolve nowhere (CV1, always an error), suite symbols that
no artifact, claim or negative test maps (CV2), non-open claims older than the
freshness window (CV3), and non-open test detectors without a mutation fixture
or exemption (CV4). Thresholds for CV2-CV4 are optional, so `make verify` fails
only on a dangling citation. The recorded 2026-11-07 measurement: `rbac_pg`
80 symbols, 67 mapped, 13 unmapped in two uncited files, 0 stale, 0 without a
fixture; `craft-i18n` 26 of 26 mapped, 0 stale, 0 without a fixture. Mapping is
file-level and symbol extraction is a narrow scanner, not an AST; the report
says which files nobody mapped, not whether a detector executes every test in a
mapped file.

Diff coverage is a separate gate (V2-07): `tools/diff_coverage.py` reads the
choke points a registry declares through `enforced_at` and checks that every one
changed in a git range maps to a non-open claim (DC1 path, DC2 symbol). An
`enforced_at` that cannot be located in the repository is always an error (DC3);
an untouched range (DC4) or a registry with no declarations (DC5) is an explicit
info, not a silent pass. Mapping is by cell `claim_ids`, claim evidence
`artifact`, or a claim/negative-test symbol; an `open` claim never counts.
Symbols now come from `tools/choke_points.py`: Python `ast`, comment/string-aware
Rust and SQL structural lexers, and an SQL statement span that covers a
dollar-quoted body. A SQL body-only edit, a Rust block-comment brace and a
Python decorator-only change are all attributed to the symbol; the token
fallback runs only when no definition is found and reads masked lines (V2-22).
The recorded 2026-11-07 measurement: `rbac_pg` `v1.3.1..HEAD`, 110 changed
files, 1 declared path and 1 symbol, 2 of 2 mapped; `craft-i18n`
`f0dd77b^..f0dd77b`, 3 files, 2 of 2 mapped. Only CELL-001 and CELL-003 declare
`enforced_at` at all, so 100 % is two declarations, not the 43 cells. The gate is
not in `make verify` — a PR gate needs a base SHA — and `ci/diff-coverage.yml`
is the untested template for one.

Choke-point extraction is a review queue, not a gate (V2-22):
`tools/choke_points.py` scans ordinary code, uses `spec/choke-points/rules.yaml`
to decide which definitions are candidates and which cell class each one would
belong to, and validates the rules against the registry schema enums. Rules are
ordered, first match wins, and a candidate that matches no rule is reported as
`unclassified` rather than forced into `other`. Python is parsed with `ast`;
Rust and SQL use comment/string-aware structural lexers, not full parsers.
Measured 2026-11-07: `rbac_pg` 75 files, 1585 definitions, 1413 candidates,
867 classified and 546 unclassified (38.6 %); `craft-i18n` 9 files, 128
definitions, 64 candidates, 47 classified and 17 unclassified (26.6 %); both
914/1477 = 61.9 % classified. The unclassified share is a measured gap in the
signal/rule file, not a taxonomy class, and no CP1 threshold is gated until the
noise is reduced. A class match is a hypothesis, not evidence that the site
enforces an invariant.

SARIF output becomes evidence through an adapter, not through trust (V2-23):
`tools/sarif_evidence.py` resolves the engine by `tool.driver.name`, maps each
result by rule ID through `spec/sarif/adapters.yaml`, and emits one finding per
unique result with its class, failure mode and optional cell. An unknown
engine, an unmapped rule, a missing rule ID or a missing location is reported
as `unmapped` with a reason; nothing falls into `other`. `--max-unmapped 0` and
`--require-engines 3` turn those counts into gates. The three inputs under
`spec/sarif/fixtures/` are **authored** documents, not captured engine runs:
each is marked `properties.dev-sec-skills/fixture = true`, the report records
`fixture_inputs: 3`, and `--reject-fixtures` refuses them in a production job.
Measured 2026-11-07 on the fixtures: 3 engines, 7 findings, 0 unmapped, 1
duplicate, 5 findings mapped to a cell and 2 to a class only. `make sarif`
exercises the fixtures and `make sarif-record` writes
`spec/sarif/2026-11-07-report.json`; neither is in `make verify`, because a
green fixture run is not evidence about a repository. The adapter proves
that the mapping and its failure paths work; it does not prove that a real
engine produces these findings, that a finding is a true positive, or that a
flagged site is unprotected.

The `unroutable` share is measurable through an escape hatch (`taxonomy_class`
or `failure_mode` = `other`, with a mandatory `routing_note`) and
`tools/unroutable.py`; `make verify` gates it at 0 %. N = 87.5 % (21/24) and
U = 0.0 % (0/43) are fixed with artifacts dated 2026-11-07 in
`conveyor/product-trials.md` §2.1. The boundary is filled, but product trials
are still not open: §5 (baseline plus the V2-33 checklist) runs at the first
product sprint, and no product run counts as improvement statistics before it.

Removal is not silent (V2-05): a claim or cell leaves a ledger only through a
top-level `retired: [{id, reason, date}]` tombstone. `status_diff` and CL6 error
when a base ID disappears without one, error when a tombstone names a live ID,
and error when an earlier tombstone is dropped. `claim_lint` L1 and `cell_lint`
CL1 reject a tombstone with no reason, a duplicate, and a live ID, so the shape
is checked even without a base.

## Reading order

1. `CONCEPT.md` — thesis, trust policy, layers, taxonomy, verdicts, ceiling.
2. `cell-registry.schema.json` — the machine-readable shape of a cell.
3. `cells.seed.yaml` — uncalibrated seed cells, all `open`.
4. `guard-grammar.md` — what L2 can and cannot model. `../../schemas/run-record.schema.json` and `../../schemas/tool-output.schema.json` — the shape of one executed run and of one tool verdict.
5. `product-trials.md` — when the solution may leave the pilot, and how an
   improvement is measured.
6. `../../tools/cell_lint.py` — the executable subset of the cell contract;
   its cases are in `../../evals/cell-lint/`.
7. `pilots/rbac_pg/README.md` and `pilots/craft-i18n/README.md` — what a real
   registry looks like and what it still cannot prove (security extension and
   a small Rust crate, two different shapes).
8. `../../Makefile` — `make verify`, the single entry point for every static
   gate.

## What this is not

- Not a certification, an audit, or a compliance statement.
- Not a throughput claim. Numbers such as review time or cell count are
  `open` until measured on a pilot.
- Not a replacement for the skills. `CONCEPT.md` depends on
  `negative-test-first`, `evidence-first-docs`, and `invariant-first-code`
  for content and evidence discipline.
