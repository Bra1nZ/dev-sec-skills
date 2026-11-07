# Dev-Sec Skills: Evidence Before Claims

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-orange)](skills/negative-test-first/SKILL.md)
[![Languages: RU / EN](https://img.shields.io/badge/docs-RU%20%2F%20EN-2ea44f)](README.md)

Agent skills for teams that need more than a green test and a confident
sentence. One working principle in three planes: **a claim exists only with
evidence, scope, and an honest status.**

The skills are not tied to a language, framework, or standard. They describe
how an agent should reason and what it should check; the references connect
those rules to international and Russian standards.

## Why this exists

Agents write positive tests well and convincing READMEs even better. They
check that code does what was asked and almost never that code refuses what
was not. The result is a green suite that proves nothing about the rule, and a
document that promises more than was verified.

These skills invert the question:

- not "does the feature work?" but "which test tried to violate it?";
- not "is the system secure?" but "who exactly failed to get through, under
  which threat model?";
- not "is everything tested?" but "which claims are still `open`, and who
  admits it?".

## The three skills

| Skill | Use when | Main output |
| --- | --- | --- |
| [`negative-test-first`](skills/negative-test-first/SKILL.md) | Test planning, coverage review, "is it done?", release gate | Every requirement paired with a test that attempts to violate it |
| [`evidence-first-docs`](skills/evidence-first-docs/SKILL.md) | README, architecture, ADR, API contracts, security/compliance claims, release notes, audit packs | Claim ledger: mechanism, evidence, scope, status, limitations |
| [`invariant-first-code`](skills/invariant-first-code/SKILL.md) | Auth, permissions, data, transactions, migrations, concurrency, APIs, secrets, supply chain | Invariant, enforcement point, fail-closed behavior, negative check |

They compose:

1. `invariant-first-code` names what must always hold.
2. `negative-test-first` tries to break it.
3. `evidence-first-docs` records what was actually proven, where, and with
   which limits.

## Shared principles

- **Claim, not mood.** "Secure" and "correct" are not claims. A claim must be
  falsifiable.
- **Negative first.** The positive test is the cheap half. Coverage starts
  with an attempt to violate.
- **Scope next to the claim.** Versions, platforms, privileged actors, and
  exclusions belong where the promise is made.
- **Status, not belief.** `proven`, `model-checked`, `tested`,
  `static-refinement`, `reviewed`, and `open` are different things.
- **An artifact is not evidence.** A report, test, or PDF does not prove
  anything without a result, a scope, and reproducibility.
- **Standard-agnostic core.** The skills do not name standards. The crosswalk
  does.

## Standards

The core draws on practices found in NIST SSDF, NIST SP 800-160, OWASP ASVS,
ISO/IEC/IEEE 29148/42010/29119, ISO/IEC 25010, CWE/SARIF, SLSA,
SPDX/CycloneDX, RFC 2119/8174, and Diátaxis.

Russian requirements — FSTEC 55, 76, 64 and GOST R 56939-2024 / 71207-2024 —
are not dissolved into the core. They live in
[`references/standards-map.md`](references/standards-map.md) with international
analogues. It is a **crosswalk, not a certification or an audit**: a mapping
table cannot declare compliance.

Downloaded freely available documents and links to paywalled ISO standards are
in [`references/standards/SOURCES.md`](references/standards/SOURCES.md).

## Concept: the verification conveyor

The [`spec/`](spec/README.md) directory is the knowledge layer of a system that
assembles these skills into a conveyor: default deny at merge, provenance as
taint, a cell taxonomy instead of an accumulating pile of lessons, a verdict
registry, and an explicit promise boundary for L2.

- [`spec/conveyor/CONCEPT.md`](spec/conveyor/CONCEPT.md) — the concept with
  claims C-01…C-26 (Russian source of truth); English derivative:
  [`CONCEPT.en.md`](spec/conveyor/CONCEPT.en.md).
- [`spec/conveyor/cell-registry.schema.json`](spec/conveyor/cell-registry.schema.json)
  — the machine-readable cell.
- [`spec/conveyor/cells.seed.yaml`](spec/conveyor/cells.seed.yaml) — 12 seed
  cells from the six invariant categories, all `open`.
- [`spec/conveyor/guard-grammar.md`](spec/conveyor/guard-grammar.md) — what L2
  can and cannot check; English derivative:
  [`guard-grammar.en.md`](spec/conveyor/guard-grammar.en.md).
- [`spec/conveyor/product-trials.md`](spec/conveyor/product-trials.md) — the
  product-trial boundary: entry criteria, metrics and measurement protocol;
  English derivative: [`product-trials.en.md`](spec/conveyor/product-trials.en.md).
  N = 87.5 % and U = 0.0 % are fixed with artifacts; trials are not open yet —
  opening needs the baseline plus the V2-33 checklist.
- [`schemas/run-record.schema.json`](schemas/run-record.schema.json) — one
  executed run: commit, command, exit code, log and artifact hashes, counts.
  Checked by L1/L2 (`claim_lint`).
- [`spec/pilots/rbac_pg/`](spec/pilots/rbac_pg/README.md) — pilot registry with
  29 cells: 26 non-open, 3 open, 0 CL1/CL3/CL4 errors. 24 of 27 detectors have a
  mutation fixture and 3 more carry a documented `mutation_exemption`
  ([`mutations/`](spec/pilots/rbac_pg/mutations/README.md)).

Phase 0 status: document, schema, `cell_lint`, and one pilot registry. There is
no production registry. Numbers such as "~200 cells" and "45 → 15 minutes" are
marked `open`: design intent, not measurement; the pilot produced 29 cells for
one extension.

## Layout

```text
skills/
  negative-test-first/
    SKILL.md
    README.md
    README.en.md
  evidence-first-docs/
    SKILL.md
    README.md
    README.en.md
    references/
      banned-words.md
      evidence-template.md
  invariant-first-code/
    SKILL.md
    README.md
    README.en.md
    references/
      invariant-template.md
      review-checklist.md
references/
  standards-map.md
  standards/
    SOURCES.md
    downloaded/
tools/
  bounded_check.py
  cell_lint.py
  choke_points.py
  claim_lint.py
  coverage_report.py
  diff_coverage.py
  fuzz_run.py
  fuzz_triage.py
  invariant_catalog.py
  mutation_plan.py
  proof_plan.py
  sarif_evidence.py
  status_diff.py
  unroutable.py
.github/
  workflows/
    fuzz-nightly.yml
ci/
  cell-lint.yml
  claim-lint.yml
  diff-coverage.yml
  mutation-changed.yml
evals/
  evals.json
  README.md
  iteration-1/
    RESULTS.md
  iteration-2/
    evals.json
    RESULTS.md
  iteration-3/
    RESULTS.md
  iteration-4/
    RESULTS.md
  linter/
    run_evals.py
    cases/
  cell-lint/
    run_evals.py
    cases/
  status-diff/
    run_evals.py
    cases/
  fuzz/
    run_evals.py
    cases/
  fuzz-triage/
    run_evals.py
    cases/
  coverage/
    run_evals.py
    cases/
  diff-coverage/
    run_evals.py
    cases/
  choke-points/
    run_evals.py
    cases/
  mutation-plan/
    run_evals.py
  invariant-catalog/
    run_evals.py
  sarif/
    run_evals.py
  bounded-check/
    run_evals.py
  proof-plan/
    run_evals.py
    mutation_selftest.py
spec/
  README.md
  conveyor/
    CONCEPT.md
    CONCEPT.en.md
    cell-registry.schema.json
    cells.seed.yaml
    guard-grammar.md
    guard-grammar.en.md
    product-trials.md
    product-trials.en.md
  fuzz/
    README.md
    corpus/claim-lint/
    runs/claim-lint-2026-11-07.json
    triage/claim-lint-2026-11-07.yaml
  coverage/
    README.md
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  diff-coverage/
    README.md
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  choke-points/
    README.md
    rules.yaml
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  invariants/
    README.md
    catalog.yaml
    2026-11-07-coverage.json
  sarif/
    README.md
    adapters.yaml
    fixtures/
    2026-11-07-report.json
  proofs/
    README.md
    manifest.yaml
  red-team/
    README.md
    run_drills.py
    2026-11-07-drills.json
  pilots/
    rbac_pg/
      cells.yaml
      README.md
      mutations/
        mutations.yaml
        run_mutations.py
        README.md
```

## Install

The skills are agent-neutral: each is a directory with a `SKILL.md`. Copy the
ones you need where your agent looks for skills.

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/negative-test-first ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

For another agent, put `SKILL.md` and its `references/` where that agent looks
for skills. The `README.md` next to a skill is for humans, not for context
loading.

## How to use

- Before a release: run `negative-test-first` over the claims and list the ones
  without a violating test.
- Before publishing a README or audit pack: run `evidence-first-docs` to
  remove unsupported absolutes and add scope.
- Before merging a security-sensitive change: run `invariant-first-code`
  through the checklist and verify the guard cannot be bypassed and the test
  fails when the guard is removed.
- After an incident: add a named lesson to a test, not only to a comment.

## Checks

Every static gate runs with one command (V2-08):

```bash
make verify
```

It runs the adversarial suites (`evals/`), CL1–CL6 over the seed registry and
over both pilot registries together with their claim ledgers, L1–L5 over the
ledgers, the status-escalation gates, and the coverage report for both pilots.
The pilots are located by `PILOT_ROOT` (defaults to `../rbac_pg`) and
`PILOT2_ROOT` (`../astraoffice/craft-i18n`); if one is missing, the command
fails instead of skipping the gate.

Diff coverage is separate from `verify` for the same reason mutation runs are:
the gate needs a base ref, while `verify` compares the working tree against this
repository's last commit. `make diff-coverage` runs DC1–DC5 over the two fixed
ranges, and `make diff-coverage-record` writes the snapshots into
`spec/diff-coverage/`. The choke-point scan is separate too: `make choke-points`
prints the review queue for both pilots, and `make choke-points-record` writes
the snapshots into `spec/choke-points/`; the CP1 threshold is not in `verify`
until the rule noise is measured and reduced.

Mutation runs are separate: `make mutations` for `rbac_pg` on a live
PostgreSQL, `make mutations-i18n` for the `craft-i18n` fixtures (cargo only),
`make mutations-all` for both, and `make verify-all` for verify plus both.

`make verify` proves internal consistency of the registries, ledgers, and evals,
not that any property holds and not that a production registry is clean. One
known gap is recorded in `evals/status-diff` (re-dating).

## Languages

- `SKILL.md` is English so the skill works in multilingual agents.
- `README.md` is Russian.
- `README.en.md` is English.
- The skills contain no language-specific annexes: examples and rules apply to
  any stack.

## Status

This is an early `0.1`: three skills, a crosswalk, evidence templates, skill
evals, twelve linter suites, and the `spec/` directory with the conveyor concept.
Results are in [`evals/iteration-1/RESULTS.md`](evals/iteration-1/RESULTS.md),
[`evals/iteration-2/RESULTS.md`](evals/iteration-2/RESULTS.md),
[`evals/iteration-3/RESULTS.md`](evals/iteration-3/RESULTS.md), and
[`evals/iteration-4/RESULTS.md`](evals/iteration-4/RESULTS.md). Planned:
executable checks for static analysis and trigger evals.

The executable part also includes `tools/claim_lint.py` (L1–L5; L2 verifies
run-record hashes, exit code, date and executed IDs, compares the artifact with
its blob at the cited commit, and checks tool-output hashes, mandatory `status` and bounds for
`model-checked`/`proven`), `tools/cell_lint.py` (CL1–CL6: structure,
coverage, evidence, traceability, taxonomy, status-escalation gate; a
`runtime-enforcement` detector needs a negative test, and the cell needs
`enforced_at`, `oracle` and `violation_response`),
`tools/unroutable.py` (the `unroutable` share) and the `ci/cell-lint.yml`
template. The linter cases are in [`evals/linter/`](evals/linter/): 40/40,
including 8 run-record cases, two V2-09 controls — `unrelated-commit` (the
commit resolves but the artifact changed after it) and `empty-claims` (an empty
ledger must fail instead of passing vacuously) — and seven V2-10 `tool-output-*`
cases (valid, output hash, missing output, non-zero exit, date, a model-checked
claim with no output, a model-checked claim with no bound) and five V2-28 cases (`unverified` at
exit 0, a timeout with a truncated log, `timed_out` contradicting the
status, a record without `status`, and an open claim that honestly keeps an
`unverified` record). The historical
12-case run is `evals/iteration-3/RESULTS.md`. The cell-lint cases are in
[`evals/cell-lint/`](evals/cell-lint/): 40/40, with a runner negative control.
These are synthetic fixtures, not proof that any production registry is clean.

The bounded run `tools/bounded_check.py` (V2-28) starts an external tool in
its own process group and kills the group at the wall-clock bound. The
`tool_output` record gains a mandatory `status`: `completed` (the process
exited before the bound), `unverified` (the bound elapsed and the group was
killed), `failed` (non-zero exit) or `error` (the supervisor could not
start). `timed_out`, `bound_seconds` and `elapsed_seconds` are recorded
explicitly; L1 rejects `timed_out` contradicting the status, and L2 forbids
`status != completed` from supporting a non-open claim. An open claim may
honestly keep an `unverified` attempt. The cases are in
[`evals/bounded-check/`](evals/bounded-check/): 10/10, including survival of
a grandchild after `killpg` and two `claim_lint` integration runs. The
supervisor classifies its own child and does not prove a real checker's
semantics; a child that leaves the group by double-forking can survive the
kill.

The fuzz adapter `tools/fuzz_run.py` (V2-17) runs a target over a seed corpus
and random mutations with a fixed seed, checks every execution against explicit
oracle rules, and writes a record shaped by `schemas/fuzz-run.schema.json`. The
committed run is
[`spec/fuzz/runs/claim-lint-2026-11-07.json`](spec/fuzz/runs/claim-lint-2026-11-07.json):
5 seed ledgers, 150 mutations, 155 executions, seed 20261107, verdict `clean`;
`make fuzz-claim-lint` replays it and compares `executions_digest`. The adapter
cases are in [`evals/fuzz/`](evals/fuzz/): 5/5. The mutator is random, without
coverage guidance: `clean` means this oracle saw nothing in this budget, not
that the target is free of bugs. The triage gate `tools/fuzz_triage.py` (V2-18)
requires every finding to become a cell, a detector and a mutation fixture — or
to be dismissed with a recorded reason; a stale entry, an unresolved cell or
fixture, and a verdict that contradicts the findings are errors. Its cases are
in [`evals/fuzz-triage/`](evals/fuzz-triage/): 13/13.

The nightly replay of the recorded run (V2-19) lives in
[`.github/workflows/fuzz-nightly.yml`](.github/workflows/fuzz-nightly.yml): cron
`30 2 * * *` plus `workflow_dispatch`, never `push`/`pull_request`, so a red run
blocks no merge. The workflow replays `make fuzz-claim-lint`, fails when
`executions_digest` moves, and uploads the `fuzz-record-<run_id>` artifact for 90
days. The first run is [42394278295](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42394278295):
success, commit `3110214`, digest `93e1af3183658aa6…`, seed 20261107, 155
executions, 0 findings. This proves determinism and input integrity, not
new-bug discovery; the nightly schedule itself has not fired yet.

Event-driven `proven` (V2-29) is `tools/proof_plan.py` plus
[`spec/proofs/manifest.yaml`](spec/proofs/manifest.yaml): each proof declares
the code, model, encoding and tooling it depends on, and a diff decides which
proofs must be re-run. The manifest is empty because no claim here is `proven`;
an empty manifest declares absence, and the planner says so instead of letting a
green gate look like coverage. `make proof-plan` resolves the merge base of
`origin/main..HEAD`. Its cases are in
[`evals/proof-plan/`](evals/proof-plan/): 36/36, and
`make proof-plan-selftest` (outside `verify`, ~80 s) mutates the planner eight
ways and requires a named case to fail each time. The planner does not verify
the record hash (`claim_lint` does) and does not prove that the model matches the
code; freshness is a timestamp comparison, so a record taken from a stale
checkout still looks fresh.

Gate strength was measured on the real artifacts (C-35):
[`spec/red-team/run_drills.py`](spec/red-team/run_drills.py) takes the craft-i18n
ledger, its recorded cargo log and the cell registry, applies one attack per
drill, and requires the expected exit code and message. 10 of 12 attacks are
blocked; two stay green and are recorded as gaps: re-dating a run (C-13) and
borrowing another claim's real tests (V2-34) — the open C-08 became `tested` on
C-01's tests with L1–L5 and `status_diff` all green. A drill that expects
`allowed` fails if a gate starts blocking, so the record cannot go stale
silently. The result is
[`spec/red-team/2026-11-07-drills.json`](spec/red-team/2026-11-07-drills.json);
the drills need the craft-i18n checkout and are not in `make verify`.

The coverage report `tools/coverage_report.py` (V2-20) proves that a cited
symbol exists (CV1, always an error) and measures suite symbols that no
artifact, claim or negative test maps (CV2), stale claims (CV3), and non-open
detectors without a mutation fixture or exemption (CV4). CV2–CV4 thresholds are
optional: `make verify` fails only on a dangling citation. The recorded
2026-11-07 measurement: `rbac_pg` has 80 symbols, 67 mapped, 13 unmapped in two
uncited files, 0 stale, 0 without a fixture; `craft-i18n` has 26 of 26 mapped,
0 stale, 0 without a fixture. Mapping is file-level and symbol extraction is a
narrow scanner, not an AST: the report shows which files nobody mapped, not
that a detector executes every test in a mapped file. Its cases are in
[`evals/coverage/`](evals/coverage/): 14/14; the measurement snapshots are in
[`spec/coverage/`](spec/coverage/README.md).

Diff coverage `tools/diff_coverage.py` (V2-07) checks only choke points
declared in `enforced_at`: a changed path or symbol without a non-open claim is
DC1/DC2, an unlocatable declaration is always DC3, and an empty range or a
registry with no declarations is an explicit DC4/DC5 info. An `open` claim never
counts as coverage. Symbols are located by `tools/choke_points.py`: Python uses
`ast` (decorators join the span); Rust and SQL use structural comment/string
lexers, and a SQL span covers the whole `CREATE ... FUNCTION ...;` including a
dollar-quoted body. A SQL body edit, a decorator-only change and a `}` in a Rust
block comment are therefore visible; the token fallback over masked lines runs
only where the parser finds no definition.
The recorded 2026-11-07 measurement: `rbac_pg` `v1.3.1..HEAD` has 110 changed
files, 1 declared path and 1 symbol, 2 of 2 mapped; `craft-i18n`
`f0dd77b^..f0dd77b` has 3 files, 2 of 2 mapped. The 100 % is two declarations
(CELL-001 and CELL-003), not 43 cells: a registry without `enforced_at` gets
DC5, not coverage. Its cases are in
[`evals/diff-coverage/`](evals/diff-coverage/): 19/19; the method and limits are
in [`spec/diff-coverage/`](spec/diff-coverage/README.md); the PR-gate template
is [`ci/diff-coverage.yml`](ci/diff-coverage.yml).

Choke-point extraction `tools/choke_points.py` (V2-22) finds structural
candidates in ordinary code and maps them to cell classes through
[`spec/choke-points/rules.yaml`](spec/choke-points/rules.yaml): signals decide
what is a candidate, rules are ordered and validated against the
`cell-registry.schema.json` enums, and a candidate with no rule is
`unclassified`, not `other` — a visible rule gap, not a taxonomy class. Measured
2026-11-07: `rbac_pg` has 75 files, 1585 definitions, 1413 candidates, 867
classified / 546 unclassified (38.6 %); `craft-i18n` has 9 files, 128
definitions, 64 candidates, 47 / 17 (26.6 %); together 914/1477 = 61.9 %
classified. Its cases are in
[`evals/choke-points/`](evals/choke-points/): 14/14; the method, measurement and
limits are in [`spec/choke-points/`](spec/choke-points/README.md); the targets
are `make choke-points` and `make choke-points-record`. The CP1 threshold is not
in `make verify` until the noise is reduced; a class match is a hypothesis, not
evidence and not a cell.

The pilot registry on a real repository is
[`spec/pilots/rbac_pg/`](spec/pilots/rbac_pg/README.md): 29 cells, 26 non-open,
3 open, 0 CL1/CL3/CL4 errors when run with the claim ledger. 24 of 27 detectors
have a mutation fixture: the named suite fails exactly on the predicted tests
when the mechanism is removed; the other 3 carry a documented
`mutation_exemption` because no mutation can break them. The rbac_pg claim
ledger covers 7 of 29 cells. A clean lint means internal consistency, not that
a property holds.

The second pilot is
[`spec/pilots/craft-i18n/`](spec/pilots/craft-i18n/README.md), deliberately
non-RBAC and non-database: a Rust crate that validates translation catalogs.
14 cells (13 tested, 1 open), 13 detectors, 12 of 13 with a mutation fixture
and one documented exemption; an 8-claim ledger with 0 L1–L5 findings. The open
CELL-002 is a real gap: Unicode Cf characters (U+202E, U+200B, U+2066) pass the
checker, while U+0007 and U+FEFF are rejected.

For now this is discipline and documentation, not a certificate or a substitute
for an audit.

## License

MIT — see [LICENSE](LICENSE). Third-party standards keep their own licenses;
see [`references/standards/SOURCES.md`](references/standards/SOURCES.md).
