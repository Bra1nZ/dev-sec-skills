# Code Verification Conveyor

> **Document status:** living concept. Most statements below are design intent
> and carry the status `open`. The Russian version is the source of truth;
> this file is a derivative translation of [`CONCEPT.md`](CONCEPT.md). When the
> two disagree, the Russian text wins.
>
> **How to read.** Start with section 0: the claim registry. Statuses follow the
> `evidence-first-docs` ladder: `proven`, `model-checked`, `tested`,
> `static-refinement`, `reviewed`, `open`. `reviewed` means "checked by reading
> an artifact in this repository"; `tested` means an executable check exists;
> `open` means intent without evidence. A status may not be raised without new
> evidence: `tools/status_diff.py` enforces that rule.

## 0. Claim registry

| ID | Claim | Mechanism | Evidence | Scope | Status | Limitations |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 | The three skills define one contract: claim → mechanism → evidence → scope → status | `SKILL.md` in three directories | `skills/*/SKILL.md`; `README.md` | Any language and agent | reviewed | Checked by reading; no automated consistency check across skills |
| C-02 | `claim_lint.py` implements checks L1–L5 over a claim ledger | Schema + linter + prose fallback scanner | `tools/claim_lint.py`; `schemas/claim-ledger.schema.json`; `evals/iteration-3/RESULTS.md`; command `python3 evals/linter/run_evals.py` | JSON/YAML ledger; `.md` prose | tested | The L5 fallback has a known accuracy gap; the commit check fails closed outside a git repository |
| C-03 | `status_diff.py` prevents raising a status without new evidence | Ledger comparison; evidence identity by (kind, commit, artifact, command, tests, date) | `tools/status_diff.py` | Two files or a git ref | reviewed | No adversarial eval set; the identity rule is a design decision |
| C-04 | The skills change an agent's answer in the intended direction | `with_skill` / `without_skill` pairs | `evals/iteration-1/RESULTS.md`; `evals/iteration-2/RESULTS.md`; `evals/README.md` | Nine synthetic tasks | reviewed | Qualitative inspection; no scored harness; small sample |
| C-05 | The linter catches a forged trace and the runner does not pass vacuously | `fake-test-id` case + runner negative control | `evals/linter/cases/fake-test-id.yaml`; `evals/iteration-3/RESULTS.md` | Synthetic fixtures | tested | 35/35 cases prove the linter contract, not that any production ledger is clean |
| C-06 | The product sells verification throughput, not tests | Layers + routing + coverage table | None | — | open | No measurement of throughput, false-positive rate, or latency; next step is to instrument a baseline on the pilot |
| C-07 | L0: an AST diff routes a PR to the affected security cells in seconds | AST extractor + code-to-cell index | None | SQL/C first | open | Extractor and index are not built; a false negative in routing is a risk; needs precision/recall measurement on the rbac_pg pilot against human labelling |
| C-08 | L1: an engine-agnostic ensemble through SARIF adapters covers cells in minutes | Adapters for SVACE/PVS/Semgrep/CodeQL and others | None | Two or three engines first | open | Adapters are not written; "SARIF" is a format, not evidence; needs a triage sample and rules that route findings into cells |
| C-09 | L2: regenerating a slice of a formal model from unannotated code works as a merge gate | Bounded guard grammar + bounded model checking / VC + completeness gate | None; language limits in `guard-grammar.md` | Only cells expressible by the grammar | open | The extractor is TCB; risk of a vacuous model; the grammar covers an authorization slice, not concurrency or transactions; the model↔code gap remains |
| C-10 | Self-mutation of the conveyor is a condition of its release | Injected defective and clean PRs + an external judge | None | Conveyor releases | open | The judge is undefined; the held-out suite is not deployed; without an external judge the check is circular |
| C-11 | The taxonomy is bounded to hundreds of cells and lessons live as fixtures | Matrix of failure class × entry point × failure mode | `spec/conveyor/cell-registry.schema.json`; `spec/conveyor/cells.seed.yaml`; `spec/pilots/rbac_pg/`; `spec/pilots/craft-i18n/` | Four taxonomies | open | "~200" is a design estimate; the rbac_pg pilot produced 29 cells for one extension (25 security, 2 correctness, 1 performance, 1 maintainability), 3 of them open; the second pilot on a Rust crate produced 14 cells (2 security, 11 correctness, 1 maintainability) with no new classes; the unroutable share is structurally 0 under the current schema and is therefore unmeasured |
| C-12 | Review time for an average PR falls from ~45 to ~15 minutes | Routing + dissolving verification into the conveyor | None | — | open | No baseline measurement; depends on language, domain, and test maturity; publish a distribution, not a point estimate |
| C-13 | The verdict registry is a hash chain with an external anchor | Hash of (commit + extractor + verifier versions + model + result), append-only | None | All verdicts | open | The anchor is not chosen; no implementation; needs a threat model for log substitution |
| C-14 | The agent-guard and Citadel building blocks transfer to the code supply chain | Broker/default-deny, taint, one-shot grants, hash-chain audit | No pointers in this repository | External repositories | open | This document does not confirm them; each block needs a "repository + path/commit" pointer |
| C-15 | No one owns the combination of PR-level provenance taint + model regeneration + self-mutation + throughput as a product | — | Preliminary survey of categories, not systematic | Market and literature | open | The prior-art sweep is incomplete; this claim must not leave the building before it is done |
| C-16 | The low/medium/high routing classifier is itself an attack surface | Rules under integrity control + masquerade tests + misroute audit | None | Router | open | Rules and quotas are undefined; without them "docs and tests → auto-merge" can be bypassed by masquerading |
| C-17 | `cell_lint.py` implements checks CL1–CL6 over the cell registry | Structure, coverage, evidence, traceability, taxonomy, escalation gate + adversarial runner | `tools/cell_lint.py`; `evals/cell-lint/`; `evals/iteration-4/RESULTS.md`; command `python3 evals/cell-lint/run_evals.py` | JSON/YAML registry; optional claim ledger and base registry | tested | 30/30 synthetic cases; no production registry; CL6 evidence identity is a design decision; structural checks are hand-coded and may drift from the schema |
| C-18 | The cell registry instantiates on a real repository, rbac_pg | 29 cells; every non-open cell links to an existing suite or the claim ledger, open cells link to recorded gaps in their limitations; artifacts resolve; CL1/CL3/CL4 have no errors | `spec/pilots/rbac_pg/cells.yaml`; `spec/pilots/rbac_pg/README.md`; `spec/pilots/rbac_pg/mutations/`; command `python3 tools/cell_lint.py --root /home/admini/projects/rbac_pg --ledger /home/admini/projects/rbac_pg/docs/claims.yaml spec/pilots/rbac_pg/cells.yaml` | One repository, rbac_pg at HEAD `492f23c` | tested | The cell-to-test meaning was checked by review, not by machine; all 10 suites were re-run on a fresh stand on 2026-11-06 (57/22/45/54/20/25/17/20/9 OK and 5 OK/2 GAP); 24/27 detectors have a mutation fixture and 3 a documented `mutation_exemption`; 22/29 cells have no claim; lint proves internal consistency, not that a property holds |
| C-19 | The cell registry instantiates on a non-RBAC, non-database repository, craft-i18n | 14 cells; every non-open cell links to an existing test, open cells link to a recorded gap; artifacts resolve; CL1–CL5 have no errors; 12/13 detectors have a mutation fixture, 1 an exemption | `spec/pilots/craft-i18n/cells.yaml`; `spec/pilots/craft-i18n/claims.yaml`; `spec/pilots/craft-i18n/mutations/`; command `python3 tools/cell_lint.py --root /home/admini/projects/astraoffice/craft-i18n --ledger /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/claims.yaml spec/pilots/craft-i18n/cells.yaml` | One Rust crate, commit `5c5c554` | tested | The ledger and registry are authored in dev-sec-skills, not in the target; 14/14 claim linkage is by construction, not coverage; the checker's rules are covered, not the apps' rendering; 12/13 fixtures, 1 exemption |
| C-20 | The linter detects re-dating and a citation of a test that never ran when evidence carries a run_record | L2 recomputes the log and artifact sha256, matches `finished_at` to the evidence date, compares the exit code and summary counts, and requires every cited ID in the log | `evals/linter/cases/run-record-*.yaml`; `spec/pilots/craft-i18n/runs/`; `tools/claim_lint.py` | Synthetic cargo/pytest fixtures and one real `craft-i18n` run | tested | Without an external anchor (C-13) a consistent record+log forgery passes; the `rbac_pg` ledger without run_records gets warnings, not verification |
| C-21 | The linter rejects an unrelated commit: the commit resolves but does not describe the artifact's current bytes | L2 compares the artifact with its blob at the cited commit (`git cat-file -e <commit>:<path>`, `git diff --quiet <commit> -- <path>`); a commit that predates the file and a file edited after the commit are errors | `evals/linter/cases/unrelated-commit.yaml`; `tools/claim_lint.py`; a run against `craft-i18n` | The pilot's git tree and a synthetic git-backed case | tested | Outside a git work tree the check is skipped, otherwise synthetic fixtures without `.git` would fail for lacking a repository; the empty model is covered by `empty-claims`, but an empty ledger is now simply an L1 error rather than a separate model
| C-22 | A claim or cell cannot be removed without a tombstone that states a reason | `retired: [{id, reason, date}]` in the ledger or registry; `status_diff` and CL6 fail when a base ID disappears without a tombstone, when a tombstone names a live ID, and when an earlier tombstone is dropped; L1/CL1 check the shape without a base | `evals/linter/cases/retired-*.yaml`; `evals/cell-lint/cases/removed-without-retired.yaml`, `removed-with-retired.yaml`, `tombstone-dropped.yaml`, `retired-without-reason.yaml`; `evals/status-diff/run_evals.py`; `tools/status_diff.py`, `tools/cell_lint.py` | Synthetic ledgers and git repositories | tested | The shape is checked without a base, the fact of removal only in the diff; the tombstone date is optional and the order of tombstones is not checked; retired entries do not enter U or the coverage count
| C-23 | A `model-checked` or `proven` status requires the tool's output, not the existence of an artifact | `evidence.tool_output` (`schemas/tool-output.schema.json`): `tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`; L1 checks the shape and commit/command agreement, L2 the output hash, the `finished_at` date and `exit_code=0` for a non-open claim, L4 the absence of `tool_output` for `model-checked`/`proven` and the absence of `bound` for `model-checked` | `evals/linter/cases/tool-output-*.yaml`, `model-checked-without-tool-output.yaml`, `model-checked-without-bound.yaml`; `schemas/tool-output.schema.json`; `tools/claim_lint.py` | Synthetic ledgers with TLC-like output | tested | The tool's semantics and the soundness of the model encoding are not checked; without an external anchor (C-13) a consistent forgery passes; the record is required only for `model-checked`/`proven`, other statuses may still carry it |
| C-24 | A `runtime-enforcement` detector is not accepted without a negative test and a declared enforcement point | `kind: runtime-enforcement` requires `negative_test` (an ID resolved through `--suite-glob`), and the cell requires `enforced_at`, `oracle` and `violation_response`; CL1 checks the shape, CL3 resolves the ID, CL2 forbids a status above `tested` | `spec/conveyor/cell-registry.schema.json`; `tools/cell_lint.py`; `evals/cell-lint/cases/runtime-enforcement-*.yaml`, `negative-test-*.yaml`; `spec/pilots/rbac_pg/cells.yaml` CELL-001; `spec/pilots/craft-i18n/cells.yaml` CELL-003 | Synthetic registries and two real cells with recorded runs | tested | The ID is resolved only when `--suite-glob` is given (otherwise info); the meaning of `violation_response` is not checked automatically; the mutation fixture remains a separate CL2 requirement |

Registry rules:

- One claim per row. The statement must be falsifiable.
- `open` always carries limitations and a next step. An empty `open` is a risk
  disguised as a plan.
- Claims about external building blocks must point to an artifact
  (repository + path or commit). Without a pointer the status stays `open`.
- Raising a status requires new evidence; a rerun with a newer date counts as
  new evidence for freshness only, not for strength of proof.

## 1. Thesis

Code generation has become free; the bottleneck is verification capacity. A
department of 10,000 juniors merging a PR per minute does not exist, but 10,000
agents already do. The product does not sell "tests"; it sells **verification
throughput**: verified PRs per unit of time at a bounded false-positive rate and
bounded latency.

"10,000 agents already do" is a statement about supply, not a measurement.
Throughput, false-positive rate, and latency stay `open` (C-06, C-12) until they
are instrumented on a pilot.

## 2. Trust policy

Origin-agnostic verification: an artifact is untrusted regardless of origin. The
equivalence "junior = agent" is correct as a trust policy (verify everything,
including senior code) and incomplete as a threat model:

- agent code has correlated errors — blind spots of the model version;
- injectable genesis — the code was shaped by texts the author did not write;
- no learning loop, which a junior has;
- no subject of responsibility.

Therefore provenance is mandatory but grants no trust. The origin label routes
checks; it does not weaken them.

## 3. Principles

1. **Default deny.** Merge and deploy are closed until verdicts are collected.
2. **Provenance as taint.** Every PR carries an origin label: model, context,
   inputs that shaped the code. The label routes checks; it does not weaken
   them.
3. **Verify the verifier.** The conveyor mutation-tests itself: an injected
   defective PR must be caught, an injected clean one must pass. This applies to
   extractors, risk classifiers, and the release judge, not only to engines.
4. **Evidence-first.** Every verdict is a ledger row {mechanism, evidence,
   scope, status}; the ledger is a hash chain with an external anchor.
5. **Taxonomy before history.** The object of audit is a bounded matrix of
   failure classes, not a growing pile of lessons.
6. **Lessons compound, folklore evaporates.** Every human judgement is compiled
   into an artifact: a detector, a contrastive pair, a specification. Review is
   a compiler of judgements into artifacts, not a stream of checks.

## 4. Verification layers

| Layer | Trigger and cost | Content |
| --- | --- | --- |
| **L0** | every PR, seconds | AST diff (`libpg_query`/`pglast` for SQL, `libclang`/`tree-sitter` for C) → whether security-relevant functions were touched → regression of negative tests and detectors for the affected cells |
| **L1** | every PR, minutes | Engine-agnostic ensemble through SARIF adapters (SVACE, PVS-Studio, Semgrep, CodeQL, clang-tidy, Infer, Bandit/ruff/gosec, SpotBugs, SCA/SLSA); findings are routed into cells; a detector for correlated failures across the PR stream; scanning of inputs that shaped the code |
| **L2** | merge gate for products with a formal model, minutes to tens of minutes | Regeneration of a **slice** of the formal model from changed functions through a bounded guard grammar; bounded model checking (`probcli`) or VC over the C layer (`SeaHorn` / `Frama-C`+`WP` → Z3); targets are stable (from the requirements registry), and their survival on the new model is checked |
| **L3** | nightly / release, hours | Full model regeneration + full model checking + Rodin round-trip; parser and state fuzzing; penetration-test simulation / BAS; self-mutation of the conveyor as a release condition |

### 4.1 Configurations

A configuration is a bundle of layers + a cell coverage matrix + model-checking
bounds.

- "Fast" — L0+L1 with a reduced ensemble.
- "Balanced" — plus L2.
- "Maximum" — L0–L3.
- "No formal model" — L0+L1+fuzzing.

The price of a configuration is its **coverage table**: "cell → covered by what →
what remains open". The client buys a concrete list of closed cells and a
concrete list of holes, not speed. The formal model, the SVACE adapter, fuzzing,
and BAS are shop modules.

### 4.2 Limits of L2

L2 is the most ambitious layer and the narrowest in applicability. The bounded
guard grammar expresses an authorization slice: roles, levels, equalities,
attribute existence, TTL. The full specification is in
[`guard-grammar.en.md`](guard-grammar.en.md) (Russian source:
[`guard-grammar.md`](guard-grammar.md)).

Consequences:

- **L2 cannot be sold as coverage of all cells.** Concurrency, partial writes,
  transactions, and the supply chain are not expressible in the grammar. For
  them L2 must return `unroutable`, not "verified".
- **The extraction completeness gate** (`code events ⊆ model events`) works only
  if the extractor is trusted. The extractor is TCB. It therefore enters
  verify-the-verifier: a mutation set where "inject a guard into code — the
  extractor must see it; remove a guard — it must see the change".
- **Vacuity check.** An empty or trivial set of model events makes the gate
  meaningless. An empty slice is a failure, not a success.
- **Unroutable bucket.** A guard outside the grammar is not discarded silently:
  merge stays closed until a human decides, and the case enters the statistics.
- **The model↔code gap remains:** the model checks predicates, not
  cryptography, the network, or storage. This is recorded in the scope of every
  verdict.

### 4.3 Price = coverage table

The same cell can be closed by different layers. The coverage table shows not
"how much was run" but "which cell is closed by what and what remains open". It
is also the interface to the client and to the auditor.

## 5. Taxonomy and detectors

### 5.1 Cell

The skeleton is a fixed matrix: **failure class × entry-point class × failure
mode**. Several taxonomies: security, correctness, maintainability,
performance. The order of magnitude is hundreds of cells, not millions of
lessons.

A cell = `{class, detector set, coverage status, residual risk, owner}`. The
machine-readable form is in
[`cell-registry.schema.json`](cell-registry.schema.json); the seed set from the
six invariant categories is in [`cells.seed.yaml`](cells.seed.yaml). All seed
cells are `open`: they fix the shape of the taxonomy, not coverage.

### 5.2 Detector

A detector is a test, an analysis rule, or a formal invariant. Every detector is
mutation-tested with its own fixture: a detector without a fixture is not
verified, even if it is green. This applies principle 3 at the cell level.

### 5.3 Audit surface

One or two pairs of senior hands per quarter:

- quarterly taxonomy review;
- statistical sample of the routing log;
- triage of the `unroutable` bucket with a quota.

An empty bucket means the taxonomy is complete on the observed stream. A filling
bucket signals an unknown unknown. Taxonomy expansion is decided by humans from
data, not by an agent.

### 5.4 Collapsing scale

10,000 lessons = 10,000 fixtures at hundreds of cells. The knowledge base is
audited through cells, not through history. The number "~200" is a design
estimate (C-11); the rbac_pg pilot produced 29 cells for one extension, but the
order of magnitude for a multi-component platform is not confirmed.

## 6. Lessons and business rules

### 6.1 Lesson object

`{id, taxonomy, cell_or_candidate, example_bad, example_good, reasons[],
measurable, detector_id?, status, owner, last_seen}`.

- Measurable reasons become detectors immediately.
- Non-measurable ones become a contrastive pair for in-context AI review and a
  fixture for a future detector.
- Repeating reasons are distilled into a new cell with human acceptance.

### 6.2 Learning channel

Code that resembles `example_bad` receives, at the moment of writing, a
bad/good pair and the reason — in the author's context and in the AI reviewer's
prompt. A senior teaches only new cases; everything else is taught by the
extracted artifact.

### 6.3 Ladder of business-rule formalization

Prose → decision table / property / BDD → DSL rule or policy (OPA/Rego, custom
DSLs) → executable specification → fixtures.

A rule = a claim in the ledger `{id, prose, spec_kind, spec, evidence, status,
owner, domain_expert}`. Humans keep two bounded steps: extracting the rule from
the domain owner's head and accepting the formalization. The unformalizable
lives in a visible backlog of open rules with a quota.

## 7. Verdicts, routing, and the human role

### 7.1 Verdict registry

A verdict record: commit hash + extractor hash + verifier versions + model hash
+ result. The log is append-only, hash-chained, externally anchored.

Anchor options (choice is C-13, open):

- transparency log: Rekor / SCITT;
- in-toto layout + Sigstore attestations;
- a separate append-only repository referenced by CI.

The anchor is needed so that rewriting the log is visible. Without an external
anchor a hash chain protects only against accidental corruption, not against
deliberate substitution.

### 7.2 Risk-based routing

After verdicts:

- low-risk (docs, configs, tests) — auto-merge when green;
- medium (business logic, style) — light review;
- high (architecture, impact) — deep review.

Classification is an attack surface (C-16): code masquerading as a test or a
config gets the easy path. Therefore classification rules:

- live under the same integrity control as the conveyor config;
- are versioned and pass their own negative tests (masquerade cases);
- enter a sampled audit of misroutes with a quota.

Auto-merge is allowed only with green verdicts; classification does not replace
verdicts.

### 7.3 Three roles of review

- **Checking** dissolves into the conveyor.
- **Teaching** becomes retrieval of contrastive pairs.
- **Lawmaking** stays with humans: new cells, acceptance of formalizations,
  taxonomy expansion.

The economics ("45 → 15 minutes") is C-12, `open`. Until measured it is a
hypothesis, not a promise. Next step: instrument a baseline on the pilot and
publish a distribution, not a point estimate.

## 8. Security of the conveyor itself

### 8.1 What is attacked

The conveyor is TCB and a target. Surfaces: the oracle, the reviewer agent
(injection), the model generator (substitution), the config (tamper), the
verdict log (rewrite), the risk classifier (masquerade).

### 8.2 Measures

- Verifiers and rule sets are pinned.
- Pin sets of publisher keys are set by a trusted party at bootstrap.
- The conveyor config is under integrity control (config-tamper pattern).
- Verdicts are an append-only hash chain with an external anchor.
- Checking, learning, and audit are separate channels: a logging failure does
  not disable checking.

### 8.3 Verify the verifier: what exactly is checked

Mutation testing applies to:

1. **Engines and rules** — an injected defect must be found.
2. **Model extractor** — an added guard must enter the model; a removed one must
   change it.
3. **Risk classifier** — masquerade cases (code disguised as a test/config) must
   route to high or enter the audit.
4. **Conveyor release judge** — see 8.4.

### 8.4 Self-mutation and the external judge

Self-mutation of the conveyor is a release condition (C-10). But the judge
cannot be the conveyor itself: that is a circular check. The minimal
construction:

- a held-out negative suite outside the conveyor repository;
- fixed seeds and versions;
- independent acceptance of the result: a second run with a different engine
  set, or a human decision against a criterion recorded in advance.

Without a named judge, the claim "the conveyor checks itself" stays `open`.

### 8.5 Goodhart

Code evolves toward the gate, not toward correctness. Measures:

- rotating held-out negative suites outside the repository;
- statistical human audit of a sample that audits **the conveyor**, not the
  code;
- periodic replacement of some detectors so that a fixed gate does not become
  the objective function.

## 9. Ceiling (honest scope)

**Not caught:**

- architectural debt with a time lag (the code is correct now, the problem
  appears after N sprints);
- business-logic errors under a wrong specification;
- scalability without load testing;
- emergent behavior of compositions;
- UX.

Theoretically: the halting problem, Rice's theorem, the model↔code gap.

**Partially caught:**

- formalized architectural antipatterns as cells (cyclic dependencies, layer
  violations);
- performance regressions through A/B baselines in CI;
- security debt through SCA.

**Complementary processes outside the system:** architecture review, load
testing, domain acceptance, integration tests, chaos. The system does not
replace them; it removes routine work and hands them artifacts.

## 10. Building blocks already in hand

| Block | What transfers | Status in this document |
| --- | --- | --- |
| agent-guard | broker/default-deny, taint/provenance, egress + approval with one-shot grants, hash-chain audit, mutation matrices, BEFORE/AFTER format | open (C-14): needs a "repository + path/commit" pointer |
| Citadel / MODEL.md | manual code→event tracing as the extractor specification; guard grammar (roles, levels, equalities, TTL); "requirements registry → goals → invariants" pipeline; experience with `probcli` and counterexamples | open (C-14): needs a pointer |
| Skills | `invariant-first-code` — cell content; `negative-test-first` — fixtures and self-checking; `evidence-first-docs` — ledger and status ladder | reviewed (C-01) |
| Financial-model discipline | a source registry for every number | reviewed as a practice; not yet applied to throughput numbers |

This document does not confirm the external blocks. It records that they are
needed and how they would fit, but evidence must come from their repositories.

## 11. Novelty gap

Preliminary survey: engines are fragmented, dashboards are consolidated, the
closed loop is unowned. Predecessors closed pieces:

- Tricorder / Error Prone — lesson → detector, reviewer feedback;
- Springfield — fuzzing as a service in CI;
- AWS Automated Reasoning — formal checks in CI for narrow domains;
- SLSA / in-toto — build provenance;
- Letta / MemGPT — hierarchical memory;
- assurance-case tooling (GSN/SACM) — argument structure, but not an executable
  merge gate.

The claimed combination: **PR-level provenance taint + model regeneration from
unannotated code as a merge gate with an extraction completeness gate +
self-mutation of the conveyor as a release condition + a top-down knowledge base
with a bounded audit surface + verification throughput as the unit of product**.

Status is `open` (C-15). Before external publication a systematic prior-art
sweep is needed, not this paragraph.

## 12. Roadmap

**Phase 0 — knowledge layer (this directory).**

- Concept with a claim registry.
- Cell registry schema and seed set.
- Guard grammar specification and its limits.
- `cell_lint` and adversarial cases: CL1–CL6, 40/40 (C-17).
- Pilot registry for rbac_pg: 29 cells, 26 non-open, 3 open, 0
  CL1/CL3/CL4 errors (C-18).
- Second pilot `craft-i18n` (Rust, non-RBAC, non-database): 14 cells,
  13 non-open, 1 open, 0 CL1–CL5 errors, 12/13 detectors with a mutation
  fixture and one documented exemption; an 8-claim ledger (C-19).
- Mutation fixtures for 24 of 27 rbac_pg detectors and 12 of 13 craft-i18n
  detectors, with reproduced baselines and the predicted failing tests
  (`spec/pilots/*/mutations/`).
- Run-record evidence (V2-01/V2-02): schema, L1/L2 checks, 8 eval cases; all 7
  craft-i18n test claims carry log and artifact hashes, the date, the exit code
  and executed IDs. L2 catches re-dating and an unexecuted citation.
- Tool-output evidence (V2-10): `model-checked` and `proven` carry the tool's
  output (`tool`, `command`, `output` + hash, `exit_code`, `finished_at`), not
  only an artifact; L4 rejects such a status without a record, and
  `model-checked` without a `bound`. 7 `tool-output-*` eval cases.
- Runtime-enforcement evidence (V2-15/V2-16): a `runtime-enforcement` detector needs
  `negative_test` (the ID resolves through `--suite-glob`), and the cell needs
  `enforced_at`, `oracle` and `violation_response`; the first real cells are
  rbac_pg CELL-001 (42501 refusal) and craft-i18n CELL-003 (Problem with a line
  number).
- Escape hatch `other` + `routing_note` and the U measurement (V2-25):
  0/43 = 0.0 %, gated at `--max-share 0` in `make verify`. N = 87.5 % and
  U = 0.0 % are fixed with artifacts dated 2026-11-07 (V2-32).
- Taxonomy calibration and a production registry are not part of phase 0.

**Phase 1.** L0+L1 on our own repositories: AST extractor, SARIF adapters for
two or three engines, security taxonomy from the `invariant-first` categories,
verdict registry.

**Phase 2.** Guard grammar + slice regeneration on the pilot (L2), extraction
completeness gate, extractor mutation set, knowledge-base router with an
`unroutable` bucket.

**Phase 3.** Conveyor self-mutation with an external judge, held-out suites,
learning channel (retrieval of contrastive pairs at the moment of writing).

**Phase 4.** Configurations as a product with a coverage matrix instead of a
price list; certification module for critical infrastructure; VC path over the C
layer (SeaHorn/Frama-C).

### 12.1 v0.2 backlog (tasks)

Not commitments and not status: a task closes only with evidence.

**P0 — evidence integrity**

- [x] V2-01. Run-record schema: commit, artifact_sha256, log_sha256, runner, command, exit_code, tests_run, tests_passed, timestamps (`schemas/run-record.schema.json`, `$ref` from `schemas/claim-ledger.schema.json`).
- [x] V2-02. `claim_lint` verifies the run record instead of string evidence: L1 checks the shape and commit/command agreement, L2 the log and artifact hashes, the `finished_at` date, the exit code, the summary counts, and that every cited ID appears in the log. 8 eval cases (`run-record-*`); all 7 `craft-i18n` test claims carry a recorded log (`spec/pilots/craft-i18n/runs/`); the `rbac_pg` ledger has no records, so its 7 L2 warnings are visible debt.
- [x] V2-03. `status_diff`: missing or unknown base ref → error; only `--first-release` is exempt.
- [x] V2-04. `cell_lint`: missing base registry → error via `--require-base`, not a gate-less run.
- [x] V2-05. A removed claim or cell is an error unless a `retired:` entry gives the reason: `retired: [{id, reason, date}]` in the ledger and registry schemas, L1/CL1 check the shape (reason, duplicate, live ID), `status_diff` and CL6 fail on removal without a tombstone and on a dropped tombstone. 3 linter cases, 4 cell-lint cases, 5 status-diff scenarios.
- [x] V2-06. CL2: missing mutation_fixture → error for security and correctness classes — warning for the other classes, and a documented `mutation_exemption` stays info (`tools/cell_lint.py`, `evals/cell-lint/cases/mutation-required-*.yaml`).
- [ ] V2-07. Diff coverage: changed choke-point paths and symbols must map to a claim.
- [x] V2-08. `make verify` as the single local entry point for all static gates: evals, the seed registry, both pilot registries with their claim ledgers, the ledgers themselves, and the status diffs (`Makefile`). Mutation runs are separate: `make mutations` (PostgreSQL stand), `make mutations-i18n` (cargo), `make mutations-all`.
- [x] V2-09. Negative controls in `evals/linter`: stub test (`fake-test-id`), re-dating (`run-record-date-mismatch`, `run-record-log-hash`), unrelated commit (`unrelated-commit`: the commit resolves but the artifact changed after it — L2 compares the artifact with its blob at the commit) and empty model (`empty-claims`: an empty ledger is an L1 error, not a vacuous pass). 25/25 cases.
- [x] V2-10. `model-checked` and `proven` require tool output, not an artifact: `schemas/tool-output.schema.json` (`tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`; optional `version`, `commit`, `verdict`, `bound`), L1 checks the shape and commit/command agreement, L2 the output hash, the `finished_at` date and `exit_code=0` for a non-open claim, L4 the absence of `tool_output` for `model-checked`/`proven` and the absence of `bound` for `model-checked`. 7 eval cases; the pilots are unaffected (they use neither status).

**P1 — enforcement**

- [ ] V2-11. `run_mutations.py` in CI for changed cells.
- [x] V2-12. Assert that the predicted IDs failed, not just any test: both runners compare the failing set with `expect_failures` exactly (`spec/pilots/rbac_pg/mutations/run_mutations.py`, `spec/pilots/craft-i18n/mutations/run_mutations.py`).
- [x] V2-13. Negative control for `tested` in security: a recorded run with the guard disabled — closed by the mutation fixtures: every tested security detector has a predicted failing run or an exemption (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-14. Mutation fixtures for the remaining pilot detectors — 25 fixtures, 24 detectors with a fixture and 3 with a documented `mutation_exemption`; all 25 matched (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-15. `enforced_at`, `oracle`, `violation_response` fields in a cell: required when a detector has `kind: runtime-enforcement`; CL1 checks the shape. First cells — `rbac_pg` CELL-001 and `craft-i18n` CELL-003.
- [x] V2-16. A `runtime-enforcement` evidence kind with a mandatory negative test: `negative_test` on the detector, CL1 requires a non-empty ID, CL3 resolves it through `--suite-glob` (6 eval cases, including unresolved and unchecked), CL2 caps the cell status at `tested`.

**P2 — continuous loop**

- [ ] V2-17. Fuzzing adapter: oracle, seed corpus, budget, fixed seed, run artifact.
- [ ] V2-18. Triage fuzzer findings → cell + detector + fixture.
- [ ] V2-19. Scheduled fuzzing that does not block merges.
- [ ] V2-20. Coverage report: unmapped symbols, stale claims, cells without a fixture.

**General-code track — beyond RBAC**

- [ ] V2-21. Invariant catalogue outside databases and roles: input validation, authn/session, secrets, lifecycle, transactions.
- [ ] V2-22. AST choke-point extractor for ordinary code and mapping to cell classes.
- [ ] V2-23. SARIF adapters for two or three engines as evidence sources.
- [x] V2-24. A second pilot on a non-RBAC codebase (web service or CLI): `craft-i18n`, a Rust crate that checks translation catalogs; 14 cells, 13 `tested` / 1 `open`, CL1–CL6 clean, 12/13 detectors with a mutation fixture, 8 claims (`spec/pilots/craft-i18n/`).
- [x] V2-25. The taxonomy was checked on a non-RBAC pilot; the `unroutable` share is measurable through an escape hatch: `taxonomy_class` or `failure_mode` = `other` with a mandatory `routing_note`, `tools/unroutable.py`, and a `--max-share 0` gate in `make verify`. Measured 0/43 = 0.0 %; before the hatch, 0 was structural (`product-trials.en.md` §2.1).
- [x] V2-26. Exit criterion met: two pilots (`rbac_pg`, `craft-i18n`), U measured (0/43), N and U fixed before the first product run, 21/24 security detectors with a fixture.

**Formal-model boundary**

- [x] V2-27. Record in `guard-grammar.md`: L2 is a model diff plus a check that stable goals survive; theorem synthesis from code is not claimed.
- [ ] V2-28. Bounded fallback for goal-survival checking: timeout → `unverified`, not "verified".
- [ ] V2-29. Proofs (`proven`) are event-driven: the trigger is a changed choke point or model, not every PR.
- [ ] V2-30. Model-sync budget: the cost of maintaining the slice per PR as a degradation metric.

**Product-trial boundary**

- [x] V2-31. Fix the boundary in `spec/conveyor/product-trials.en.md`: entry criteria and the measurement protocol; numbers only after measurement.
- [x] V2-32. The threshold inputs were measured and recorded in `product-trials.en.md` §2.1 with artifacts: N = 87.5 % (21/24), U = 0.0 % (0/43), date 2026-11-07.
- [ ] V2-33. Fill the boundary checklist when the first product sprint opens; product runs before that do not count as statistics.

## 13. Open questions and next evidence

1. **Pilot.** rbac_pg is chosen; the pilot registry is built (C-18): 29
   cells, 0 CL1/CL3/CL4 errors. All ten suites were re-run on a fresh stand on
   2026-11-06; 24 of 27 detectors have a mutation fixture and 3 more have a
   documented `mutation_exemption`; CL2 has no warnings. The second pilot
   `craft-i18n` (Rust, non-RBAC, non-database) was built on 2026-11-06:
   14 cells, 12/13 detectors with a fixture, 8 claims, 0 errors; its open
   CELL-002 records a real gap with Unicode Cf characters. Still open: whether
   the claim ledger covers more than the FSTEC matrix. Without that,
   C-07…C-12 remain hypotheses.
2. **Verdict anchor.** Rekor/SCITT, in-toto+Sigstore, or an append-only
   repository. Needs a threat model and operating cost.
3. **Self-mutation judge.** Who accepts that a defective PR was caught, and by
   what criterion.
4. **Taxonomy calibration.** How many cells are actually used, what share is
   `unroutable`, how long the quarterly review takes.
5. **Economics.** Baseline review time, false-positive rate, latency. Publish a
   distribution, not an average.
6. **Prior-art sweep.** A systematic review before external publication of
   C-15.
7. **Extractor qualification.** Mutation set, vacuity check, limits of
   applicability.
8. **Risk classifier.** Masquerade cases and misroute audit quotas.

## Appendix A. Relation to repository artifacts

| Artifact | Role in the concept |
| --- | --- |
| `skills/invariant-first-code/` | Cell content: invariant categories, enforcement points, fail-closed |
| `skills/negative-test-first/` | Detector fixtures and verifier self-checking |
| `skills/evidence-first-docs/` | Verdict format and status ladder |
| `schemas/claim-ledger.schema.json` | Prototype of the verdict registry |
| `tools/claim_lint.py` | Checks L1–L5 that `cell_lint` will reuse |
| `tools/cell_lint.py` | Checks CL1–CL6 over the cell registry |
| `tools/status_diff.py` | Ban on status escalation without new evidence |
| `evals/linter/` | Example adversarial set for detectors |
| `evals/cell-lint/` | Adversarial set for `cell_lint` |
| `spec/conveyor/cell-registry.schema.json` | Machine-readable cell |
| `spec/pilots/rbac_pg/` | Pilot registry: 29 cells on a real repository |
| `spec/pilots/craft-i18n/` | Second pilot: 14 cells on a Rust crate, non-RBAC and non-database |
| `spec/conveyor/guard-grammar.en.md` | Limits of L2 |
| `spec/conveyor/product-trials.en.md` | Product-trial boundary: entry criteria, metrics and measurement protocol (draft) |
| `Makefile` | `make verify` as the single entry point for static gates (V2-08); `make mutations` (PostgreSQL stand), `make mutations-i18n` (cargo) and `make mutations-all` for the mutation suites |

This document is not a certification, an audit, or a coverage promise. It
records intent, limits, and the next evidence.
