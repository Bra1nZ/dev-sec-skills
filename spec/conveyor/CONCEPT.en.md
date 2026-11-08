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
| C-02 | `claim_lint.py` implements checks L1–L6 over a claim ledger | Schema + linter + prose fallback scanner | `tools/claim_lint.py`; `schemas/claim-ledger.schema.json`; `evals/iteration-3/RESULTS.md`; command `python3 evals/linter/run_evals.py` | JSON/YAML ledger; `.md` prose | tested | The L5 fallback has a known accuracy gap; the commit check fails closed outside a git repository |
| C-03 | `status_diff.py` prevents raising a status without new evidence | Ledger comparison; evidence identity by (kind, commit, artifact, command, tests, date) | `tools/status_diff.py` | Two files or a git ref | reviewed | No adversarial eval set; the identity rule is a design decision |
| C-04 | The skills change an agent's answer in the intended direction | `with_skill` / `without_skill` pairs | `evals/iteration-1/RESULTS.md`; `evals/iteration-2/RESULTS.md`; `evals/README.md` | Nine synthetic tasks | reviewed | Qualitative inspection; no scored harness; small sample |
| C-05 | The linter catches a forged trace and the runner does not pass vacuously | `fake-test-id` case + runner negative control | `evals/linter/cases/fake-test-id.yaml`; `evals/iteration-3/RESULTS.md` | Synthetic fixtures | tested | 53/53 cases prove the linter contract, not that any production ledger is clean |
| C-06 | The product sells verification throughput, not tests | Layers + routing + coverage table | None | — | open | No measurement of throughput, false-positive rate, or latency; next step is to instrument a baseline on the pilot |
| C-07 | L0: an AST diff routes a PR to the affected security cells in seconds | AST extractor + code-to-cell index | None | SQL/C first | open | Extractor and index are not built; a false negative in routing is a risk; needs precision/recall measurement on the rbac_pg pilot against human labelling |
| C-08 | L1: an engine-agnostic ensemble through SARIF adapters covers cells in minutes | Adapters for SVACE/PVS/Semgrep/CodeQL and others | `spec/static-analysis/two-engine-2026-11-07.md`; Bandit 1.9.4 + Semgrep OSS 1.184.0 over `rbac_pg/setup` `d978609`; 249 findings, 2 engines in one report, 0 unmapped, 0 fixtures, 0 cell_mapped, 10.018 s; 2026-11-08 triage: 249 `not-a-bug`, 0 cells | Two or three engines first | open | Two engines (Bandit, Semgrep); SVACE/PVS are unverified; the 249 findings were triaged on 2026-11-08 and all are `not-a-bug`, none is routed, so `covered`/`new` are not proved here — the only real `new` is the self-pilot (C-40) and the only real `covered` is the craft-i18n cross-pilot route; no finding received a cell: the engine `failure_class` (`invalid-or-injected-input`) differs from the invariant cells' `failure_class` (`code-injection`, `input-validation`), so the mapping is class-only; B602 found nothing; the Semgrep rule is one authored text rule (MIT), not a benchmark; Bandit exits 1 when it has findings (the 2026-11-08 record adds `--exit-zero`, so its exit code is 0); "SARIF" is a format, not evidence; the two SARIF files and the report of the 2026-11-07 measurement are not anchored — the 2026-11-08 per-engine records are (C-40/C-41) |
| C-09 | L2: regenerating a slice of a formal model from unannotated code works as a merge gate | Bounded guard grammar + bounded model checking / VC + completeness gate | None; language limits in `guard-grammar.md` | Only cells expressible by the grammar | open | The extractor is TCB; risk of a vacuous model; the grammar covers an authorization slice, not concurrency or transactions; the model↔code gap remains |
| C-10 | Self-mutation of the conveyor is a condition of its release | Injected defective and clean PRs + an external judge | None | Conveyor releases | open | The judge is undefined; the held-out suite is not deployed; without an external judge the check is circular |
| C-11 | The taxonomy is bounded to hundreds of cells and lessons live as fixtures | Matrix of failure class × entry point × failure mode | `spec/conveyor/cell-registry.schema.json`; `spec/conveyor/cells.seed.yaml`; `spec/pilots/rbac_pg/`; `spec/pilots/craft-i18n/` | Four taxonomies | open | "~200" is a design estimate; the rbac_pg pilot produced 29 cells for one extension (25 security, 2 correctness, 1 performance, 1 maintainability), 3 of them open; the second pilot on a Rust crate produced 14 cells (2 security, 11 correctness, 1 maintainability) with no new classes; the unroutable share is structurally 0 under the current schema and is therefore unmeasured |
| C-12 | Review time for an average PR falls from ~45 to ~15 minutes | Routing + dissolving verification into the conveyor | None | — | open | No baseline measurement; depends on language, domain, and test maturity; publish a distribution, not a point estimate |
| C-13 | The verdict registry is a hash chain with an external anchor | Hash of (commit + extractor + verifier versions + model + result), append-only | C-41: an SSH signature over a record's canonical bytes; three evidence channels are anchored — static-analysis (`dev-sec-skills-static-analysis`), run_record (`dev-sec-skills-run-record`) and sanitizer (`dev-sec-skills-sanitizer`), each under its own namespace; `tools/anchor_subject.py`; `tools/anchor_run.py --channel`; `spec/anchor/allowed_signers`. V2-39: an append-only verdict journal `spec/journal/verdicts.jsonl` (one canonical JSON line per verdict, `seq/date/ledger/claim/status/evidence/prev/hash`) and a signed head `spec/journal/head.json{,.sig}` (namespace `dev-sec-skills-verdict-journal`, the file hash plus the exact bytes of every ledger); `tools/verdict_journal.py verify|append` (J1 chain, J2 ledger agreement, J3 prefix against git-ref, J4 canonical head + signature); `make journal` | All verdicts | open | The journal closes the past of a verdict: editing, dropping or truncating an entry, changing a status or the evidence set without an append, substituting the head and a foreign signer are all caught by J1–J4, and append refuses to continue a broken chain or head. Only the two in-repo ledgers are covered (12 verdicts: the 2026-11-08 backfill plus C-42, date = the day it was journaled): the external `../rbac_pg/docs/claims.yaml` is deliberately outside the journal; proof and review records are not anchored, so an edit inside them changes no evidence identity; the key holder, replacement of `allowed_signers` and re-signing together with a git history rewrite bypass everything (red-team drill `rewrite-journal-and-resign` is recorded as allowed); there is no transparency log, timestamping or key revocation. Three evidence channels are implemented (C-41): offline ed25519 signature, private key outside the repository |
| C-14 | The agent-guard and Citadel building blocks transfer to the code supply chain | Broker/default-deny, taint, one-shot grants, hash-chain audit | No pointers in this repository | External repositories | open | This document does not confirm them; each block needs a "repository + path/commit" pointer |
| C-15 | No one owns the combination of PR-level provenance taint + model regeneration + self-mutation + throughput as a product | — | Preliminary survey of categories, not systematic | Market and literature | open | The prior-art sweep is incomplete; this claim must not leave the building before it is done |
| C-16 | The low/medium/high routing classifier is itself an attack surface | Rules under integrity control + masquerade tests + misroute audit | None | Router | open | Rules and quotas are undefined; without them "docs and tests → auto-merge" can be bypassed by masquerading |
| C-17 | `cell_lint.py` implements checks CL1–CL6 over the cell registry | Structure, coverage, evidence, traceability, taxonomy, escalation gate + adversarial runner | `tools/cell_lint.py`; `evals/cell-lint/`; `evals/iteration-4/RESULTS.md`; command `python3 evals/cell-lint/run_evals.py` | JSON/YAML registry; optional claim ledger and base registry | tested | 30/30 synthetic cases; no production registry; CL6 evidence identity is a design decision; structural checks are hand-coded and may drift from the schema |
| C-18 | The cell registry instantiates on a real repository, rbac_pg | 29 cells; every non-open cell links to an existing suite or the claim ledger, open cells link to recorded gaps in their limitations; artifacts resolve; CL1/CL3/CL4 have no errors | `spec/pilots/rbac_pg/cells.yaml`; `spec/pilots/rbac_pg/README.md`; `spec/pilots/rbac_pg/mutations/`; command `python3 tools/cell_lint.py --root /home/admini/projects/rbac_pg --ledger /home/admini/projects/rbac_pg/docs/claims.yaml spec/pilots/rbac_pg/cells.yaml` | One repository, rbac_pg at HEAD `492f23c` | tested | The cell-to-test meaning was checked by review, not by machine; all 10 suites were re-run on a fresh stand on 2026-11-06 (57/22/45/54/20/25/17/20/9 OK and 5 OK/2 GAP); 24/27 detectors have a mutation fixture and 3 a documented `mutation_exemption`; 22/29 cells have no claim; lint proves internal consistency, not that a property holds |
| C-19 | The cell registry instantiates on a non-RBAC, non-database repository, craft-i18n | 14 cells; every non-open cell links to an existing test, open cells link to a recorded gap; artifacts resolve; CL1–CL5 have no errors; 12/13 detectors have a mutation fixture, 1 an exemption | `spec/pilots/craft-i18n/cells.yaml`; `spec/pilots/craft-i18n/claims.yaml`; `spec/pilots/craft-i18n/mutations/`; command `python3 tools/cell_lint.py --root /home/admini/projects/astraoffice/craft-i18n --ledger /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/claims.yaml spec/pilots/craft-i18n/cells.yaml` | One Rust crate, commit `5c5c554` | tested | The ledger and registry are authored in dev-sec-skills, not in the target; 14/14 claim linkage is by construction, not coverage; the checker's rules are covered, not the apps' rendering; 12/13 fixtures, 1 exemption |
| C-20 | The linter detects re-dating and a citation of a test that never ran when evidence carries a run_record | L2 recomputes the log and artifact sha256, matches `finished_at` to the evidence date, compares the exit code and summary counts, and requires every cited ID in the log | `evals/linter/cases/run-record-*.yaml`; `spec/pilots/craft-i18n/runs/`; `tools/claim_lint.py` | Synthetic cargo/pytest fixtures and one real `craft-i18n` run | tested | Without an external anchor (C-13) a consistent record+log forgery passes; the `rbac_pg` ledger without run_records gets warnings, not verification |
| C-21 | The linter rejects an unrelated commit: the commit resolves but does not describe the artifact's current bytes | L2 compares the artifact with its blob at the cited commit (`git cat-file -e <commit>:<path>`, `git diff --quiet <commit> -- <path>`); a commit that predates the file and a file edited after the commit are errors | `evals/linter/cases/unrelated-commit.yaml`; `tools/claim_lint.py`; a run against `craft-i18n` | The pilot's git tree and a synthetic git-backed case | tested | Outside a git work tree the check is skipped, otherwise synthetic fixtures without `.git` would fail for lacking a repository; the empty model is covered by `empty-claims`, but an empty ledger is now simply an L1 error rather than a separate model
| C-22 | A claim or cell cannot be removed without a tombstone that states a reason | `retired: [{id, reason, date}]` in the ledger or registry; `status_diff` and CL6 fail when a base ID disappears without a tombstone, when a tombstone names a live ID, and when an earlier tombstone is dropped; L1/CL1 check the shape without a base | `evals/linter/cases/retired-*.yaml`; `evals/cell-lint/cases/removed-without-retired.yaml`, `removed-with-retired.yaml`, `tombstone-dropped.yaml`, `retired-without-reason.yaml`; `evals/status-diff/run_evals.py`; `tools/status_diff.py`, `tools/cell_lint.py` | Synthetic ledgers and git repositories | tested | The shape is checked without a base, the fact of removal only in the diff; the tombstone date is optional and the order of tombstones is not checked; retired entries do not enter U or the coverage count
| C-23 | A `model-checked` or `proven` status requires the tool's output, not the existence of an artifact | `evidence.tool_output` (`schemas/tool-output.schema.json`): `tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`, mandatory `status`; L1 checks the shape and commit/command agreement, L2 the output hash, the `finished_at` date, `exit_code=0` and `status=completed` for a non-open claim (V2-28), L4 the absence of `tool_output` for `model-checked`/`proven` and the absence of `bound` for `model-checked` | `evals/linter/cases/tool-output-*.yaml`, `model-checked-without-tool-output.yaml`, `model-checked-without-bound.yaml`; `schemas/tool-output.schema.json`; `tools/claim_lint.py` | Synthetic ledgers with TLC-like output | tested | The tool's semantics and the soundness of the model encoding are not checked; without an external anchor (C-13) a consistent forgery passes; the record is required only for `model-checked`/`proven`, other statuses may still carry it; `status` is the supervisor's classification, not the tool's |
| C-24 | A `runtime-enforcement` detector is not accepted without a negative test and a declared enforcement point | `kind: runtime-enforcement` requires `negative_test` (an ID resolved through `--suite-glob`), and the cell requires `enforced_at`, `oracle` and `violation_response`; CL1 checks the shape, CL3 resolves the ID, CL2 forbids a status above `tested` | `spec/conveyor/cell-registry.schema.json`; `tools/cell_lint.py`; `evals/cell-lint/cases/runtime-enforcement-*.yaml`, `negative-test-*.yaml`; `spec/pilots/rbac_pg/cells.yaml` CELL-001; `spec/pilots/craft-i18n/cells.yaml` CELL-003 | Synthetic registries and two real cells with recorded runs | tested | The ID is resolved only when `--suite-glob` is given (otherwise info); the meaning of `violation_response` is not checked automatically; the mutation fixture remains a separate CL2 requirement |
| C-25 | A fuzz run is reproducible and bounded by an explicit oracle and budget | `tools/fuzz_run.py`: the corpus is read in sorted order, the mutator is `random.Random(seed)`, `executions_digest` is the SHA-256 of the ordered input hashes; oracle rules `exit:N`, `exit-not-in:`, `stdout-contains:`, `stderr-contains:`, `timeout` are OR-ed; the record shaped by `schemas/fuzz-run.schema.json` carries the corpus manifest, budget, seed and every finding with its log | `spec/fuzz/runs/claim-lint-2026-11-07.json`; `evals/fuzz/`; `make fuzz-claim-lint` | `claim_lint` as the target, 5 seed ledgers, 150 mutations, seed 20261107 | tested | The mutator is random, without coverage guidance; `clean` means the oracle saw nothing in this budget, not that the target is bug-free; the digest binds the inputs, not the target's behaviour; the replay is not part of `make verify` (about a minute) and runs on demand |
| C-26 | A fuzz finding does not disappear: it becomes a cell, a detector and a fixture, or is dismissed with a reason, and a gate checks it | `tools/fuzz_triage.py`: T1 the triage shape, T2 exactly one entry per finding (untriaged, duplicate and stale are errors), T3 the cell and detector resolve in the registry the triage names and the fixture ID in the mutations file, T4 the record's verdict agrees with `findings`; an empty triage is accepted only for a clean run | `schemas/fuzz-triage.schema.json`; `spec/fuzz/triage/claim-lint-2026-11-07.yaml`; `evals/fuzz-triage/`; `make check-fuzz-triage` | Synthetic records; the recorded `claim_lint` run has no findings | tested | The gate has not yet run on a real finding; choosing `covered` over `new` is a review judgment, the gate only proves the artifacts exist; injecting a finding into a copy of the record in `/tmp` makes it exit 1, the repository artifact is untouched |
| C-27 | Registry coverage is measured, not assumed: dangling citations, unmapped symbols, stale claims and detectors without a fixture are visible | `tools/coverage_report.py`: CV1 a symbol cited by a claim or a detector must exist in the suite (always an error); CV2 suite symbols no artifact, claim or `negative_test` maps (info, an error only above `--max-unmapped`); CV3 a non-open claim older than `--max-age-days` (90 by default) or without a date; CV4 a non-open `test`/`runtime-enforcement` detector without `mutation_fixture` and without `mutation_exemption`; mapping is file-level and extraction uses narrow patterns `report("F3a")`, `def test_*`, `#[test] fn` | `tools/coverage_report.py`; `evals/coverage/`; `spec/coverage/README.md`; `make coverage` | `rbac_pg`: 80 symbols, 67 mapped, 13 unmapped in two files; `craft-i18n`: 26/26 mapped; 0 stale, 0 without a fixture | tested | File-level mapping does not prove a detector executes every test in a mapped file; the scanner is not an AST; without thresholds CV2–CV4 stay a report, not a gate; staleness is judged by date without an external anchor |
| C-28 | A changed choke point does not disappear from review: a path or symbol declared in `enforced_at` must map to a non-open claim, or the gate fails | `tools/diff_coverage.py`: DC1 a changed declared path without a non-open claim, DC2 a changed declared symbol without a non-open claim, DC3 `enforced_at` cannot be located in the repository (no leading `path:line`, the path is absent as a blob at base and head, or the path escapes the root) and is always an error, DC4 no changed declaration in the range, DC5 the registry declares no `enforced_at`; mapping is cell `claim_ids` → non-open claim, or a claim's `artifact` == the path, or `tests`/`negative_test` == the symbol; an `open` claim never counts; symbols are located by `tools/choke_points.py`: Python `ast` (decorators join the span), Rust and SQL structural comment/string lexers, and a SQL statement span that covers the whole `CREATE ... FUNCTION ...;` including a dollar-quoted body; the token fallback runs only when the parser finds no definition and reads masked lines | `tools/diff_coverage.py`; `tools/choke_points.py`; `evals/diff-coverage/`; `spec/diff-coverage/README.md`; `ci/diff-coverage.yml`; `make diff-coverage` | `rbac_pg` `v1.3.1..HEAD`: 110 files, 2/2 mapped; `craft-i18n` `f0dd77b^..f0dd77b`: 2/2 mapped; `--max-unmapped 0` | tested | Only cells with `enforced_at`: the 100 % is two declarations out of 43 cells, and a registry with no declarations gets DC5, not coverage; Rust macros/generated code and SQL `BEGIN ATOMIC`/quoted identifiers can still distort a span; unknown extensions keep the comment false positives; mapping does not check claim freshness; the CI template has not run on a real PR; the threshold is aggregate over paths and symbols |
| C-29 | Ordinary code yields structural choke-point candidates, and each candidate either maps to a cell class or is explicitly `unclassified` | `tools/choke_points.py`: Python uses `ast` (decorators start the span); Rust and SQL use masking lexers for comments, strings, raw/byte strings, char literals and dollar quotes, then `fn`/brace matching and top-level `;` splitting; a SQL span is the whole statement, so a body edit is visible. `spec/choke-points/rules.yaml`: `signals` decide what is a candidate, `rules` are ordered (first match wins) and validated against the `cell-registry.schema.json` enums; `other` is forbidden in a rule; a candidate with no rule is `unclassified`, not a cell. CP1/CP2 are optional thresholds over unclassified candidates and parse errors | `tools/choke_points.py`; `spec/choke-points/rules.yaml`; `spec/choke-points/README.md`; `evals/choke-points/`; `make choke-points` | `rbac_pg` 2026-11-07: 75 files, 1585 definitions, 1413 candidates, 867 classified / 546 unclassified (38.6 %); `craft-i18n`: 9 files, 128 definitions, 64 candidates, 47 / 17 (26.6 %); both: 914/1477 = 61.9 % classified | tested | Signals/rules are regular expressions over the name, calls, decorators, path and kind, with no semantics or data flow; Rust/SQL are lexers, not parsers, so macros/generated code and `BEGIN ATOMIC`/quoted identifiers are outside the grammar; `guard-call` conflates a sink (`read`, `write`, `execute`) with a guard, hence the measured 38 % unclassified; the threshold is not in `make verify`; a class match is a hypothesis, not evidence and not a cell |

| C-30 | A changed code region runs only its own mutation fixtures, and a changed cell without a fixture and exemption does not pass the plan | `tools/mutation_plan.py`: `base..head` diff through `git diff --name-status -M`; a cell is selected by `enforced_at` (the path in the sentence), a detector `artifact`, a fixture `artifact` or a changed registry entry (`--cells-base`); a fixture is selected by its cell or artifact; `--require-fixtures` returns 1 for a changed non-open cell without a fixture and without `mutation_exemption`; both runners accept `--plan` and `--only-cell`, and an empty plan exits 0 without starting a stand; `ci/mutation-changed.yml` resolves the merge base and skips the job on an empty plan | `tools/mutation_plan.py`; `evals/mutation-plan/`; `ci/mutation-changed.yml`; `Makefile` (`make mutation-plan`); both `run_mutations.py` | 13/13 eval cases; `rbac_pg` `v1.3.1..HEAD`: 110 files, 26 cells, 25/25 fixtures; `craft-i18n` `f0dd77b^..f0dd77b`: 3 files, 6 cells, 7/12 fixtures; 0 uncovered | tested | File-level mapping: editing a file selects every cell that names it even when the changed line is unrelated to the invariant; the `enforced_at` path is extracted by a regular expression, not a parser; a new fixture is not selected unless its artifact/cell or `mutations.yaml` changed (a full run is `--all`); the CI template has not run on a real PR; `--require-fixtures` does not prove a fixture is sensitive to that specific edit |

| C-31 | The invariant catalogue outside databases and roles is complete across the five categories and leaves no seed cell without a reference or an explicit out_of_scope entry | `tools/invariant_catalog.py`: INV1 exactly five categories with at least two invariants each; INV2 required fields, unique IDs whose prefix matches the category, enums from `cell-registry.schema.json`, `other` forbidden, at least two bypasses; INV3 the category, seed cell, choke-point rule and out_of_scope cell exist, and referenced/out_of_scope may not overlap; INV4 a non-open invariant names an existing `evidence_path`; INV5 every seed cell is referenced or out_of_scope and unused rules are printed as info | `spec/invariants/catalog.yaml`; `spec/invariants/README.md`; `schemas/invariant-catalog.schema.json`; `tools/invariant_catalog.py`; `evals/invariant-catalog/`; `make invariants` | 15 eval cases; 15 invariants, 5 categories; 9/12 seed cells referenced + 3 out_of_scope; 9/11 rules used; 0 errors | tested | Checks internal consistency and reference resolution, not the truth of an invariant; `failure_class` is a free string, so a typo is not caught; all 15 invariants are `open` and no negative test has run; seed cells CELL-001/002 (database roles) and CELL-011 (supply chain) are excluded by the boundary; `migration` and `sql-rls` are deliberately uncovered; two bypasses are a minimum, not a threat model |

| C-32 | Engine SARIF output becomes evidence through an adapter: an unknown engine or rule is visible as `unmapped`, and an authored fixture is not passed off as an engine run | `tools/sarif_evidence.py`: the engine resolves by `tool.driver.name` (or id, case-insensitively); rules are ordered and the first regex match on the rule ID wins; `taxonomy_class` and `failure_mode` are validated against `cell-registry.schema.json` before any input is read and `other` is forbidden; `cell` is optional as `<registry>/<CELL-ID>`, must resolve, and requires the rule's `failure_class` to equal the cell's (a cell without a `failure_class` cannot be named); otherwise the run exits 2; findings are deduplicated by `(engine, partialFingerprints)` or `(rule, path, start, end, message)`, sorted deterministically and assigned `F-NNN`; the digest is the sha256 of the ordered normalized findings; `unmapped` reasons are `unknown-engine`, `unmapped-rule`, `missing-rule-id` and `missing-location`; gates `--max-unmapped` and `--require-engines`; provenance `properties.dev-sec-skills/fixture` and `--reject-fixtures`; exit 0/1/2 | `tools/sarif_evidence.py`; `spec/sarif/adapters.yaml`; `spec/sarif/fixtures/`; `spec/sarif/README.md`; `spec/sarif/2026-11-07-report.json`; `schemas/sarif-evidence.schema.json`; `evals/sarif/`; `Makefile` (`make sarif`, `make sarif-record`) | 20/20 eval cases; 3 engines, 7 findings, 0 unmapped, 1 duplicate, 0 findings with a cell (all 7 class-only); digest `caf2a4f9fe24ba42`; inputs are authored fixtures, `fixture_inputs: 3` | tested | The fixtures are hand-written: there is no real Semgrep/CodeQL/Bandit run, and the mapping rate on real output is unknown; rule IDs change between engine versions; a mapped finding proves neither a true positive nor that the site is unprotected; no adapter rule names a cell today, so the cell path is exercised only by synthetic eval cases; the first regex match shadows later rules; deduplication by `partialFingerprints` or an exact tuple may merge distinct findings; `uriBaseId` (`%SRCROOT%`) is not resolved, the path is only rebased from `--root`; the SARIF schema is not validated; `make sarif` is not part of `make verify` |
| C-33 | A bounded run of an external tool records how it ended: a timeout yields `unverified` and cannot support a non-open claim | `tools/bounded_check.py`: `Popen(start_new_session=True)`, `killpg(SIGKILL)` at the wall-clock bound, combined stdout/stderr with no supervisor inserts, `status` out of four values, exit 0/1/2/3; `schemas/tool-output.schema.json` requires `status` and describes `timed_out`, `bound_seconds` and `elapsed_seconds`; L1 rejects `timed_out` contradicting the status, L2 rejects `status != completed` and `timed_out` for a non-open claim | `tools/bounded_check.py`; `schemas/tool-output.schema.json`; `tools/claim_lint.py`; `evals/bounded-check/`; `evals/linter/cases/tool-output-{unverified-zero-exit,timed-out,status-contradiction,missing-status,open-unverified}.yaml`; `spec/conveyor/guard-grammar.en.md` §6.6 | Synthetic child processes (`python -c`) and synthetic ledgers; no real engine was run | tested | It checks classification of its own child, not the correctness of a real checker; a child can spawn outside the process group (double-fork/setsid) and survive the kill; the bound is not adaptive; a non-zero verdict needs an adapter; `verdict` is not synthesized by the supervisor; distributed checkers and checkpoints are not covered |
| C-34 | A `proven` proof is re-run when its own object changes, not on every PR | A dependency manifest plus a planner over a git range: `artifact`, `depends_on`, `model`, `encoding` and `tooling` are matched against the diff (renames through the old path); `manifest-changed`/`proof-added` compare the manifest with a base copy; `record-not-completed` fires on any `status != completed`; freshness is `finished_at` >= the committer time of the last change to a declared path; gates `--require-fresh` and `--require-complete`, exit 2 on broken input | `tools/proof_plan.py`; `schemas/proof-manifest.schema.json`; `spec/proofs/`; `evals/proof-plan/` 36/36; `python3 evals/proof-plan/mutation_selftest.py` 8/8; a demo manifest over the real range `a50fbda..HEAD` | git range `base..head`; a JSON record with `status` and `finished_at`; paths under `--repo` or absolute | tested | Proven on synthetic git repositories and one demo manifest; no real `proven` claim exists and no real proof was re-run; the manifest is the scope, so an undeclared shared helper is invisible; freshness compares timestamps and does not check which checkout produced the record; `claim_lint` verifies the record hash and nothing verifies the checker's semantics; `--require-complete` only sees proof extensions |
| C-35 | Attacks on the real pilot artifacts are blocked by the gates, except one recorded silent path (replacing the signer) | 20 drills: a copy of the real ledger, recorded log and registry, one mutation per drill, the real tool, and a check of both the exit code and the expected message; an `allowed` drill fails if the gate starts blocking | `spec/red-team/run_drills.py`; `spec/red-team/2026-11-08-drills.json`; `make red-team` | The craft-i18n ledger (9 claims), its recorded cargo log and the cell registry; `claim_lint --no-vale`, `status_diff`, `cell_lint`, `proof_plan` | tested | One pilot; L5 is not exercised; the edits are static, so compromised tools and CI are out of scope; a block proves the specific check fired, not the absence of other bypasses; one gap remains: re-dating with a replaced `allowed_signers` and a fresh signature (C-13), while plain re-dating is blocked by the run-record anchor; borrowed evidence is closed by L6 (C-36); hiding a finding line is closed by L2 (C-37), hiding a static finding by L2 (C-40), forging a signed record by the anchor (C-41), including editing a signed run_record (L2) |
| C-36 | A test cited by two claims is declared shared with a reason, and a non-open claim has at least one test of its own | L6 in `claim_lint`: a test ID → claims map; rule 1 requires `evidence[].shared_tests: [{id, reason}]` in every citing claim; rule 2 rejects a non-open claim whose every test another claim also cites, even when the sharing is declared; L1 checks the shape (id from `tests`, non-empty reason, `kind=test` only) and `claim-ledger.schema.json` describes the field | `tools/claim_lint.py`; `schemas/claim-ledger.schema.json`; `evals/linter/cases/shared-*.yaml` (6 cases); `spec/pilots/craft-i18n/claims.yaml`; `spec/red-team/run_drills.py`; `make verify` | The craft-i18n ledger (9 claims, 21 test IDs, 1 shared test) and rbac_pg (7 claims, 22 test IDs, no shared tests); synthetic cases; two red-team drills on the real ledger | tested | Does not check that the test's assertions match the claim's wording: rule 2 stops only a fully borrowed set, so one own-but-irrelevant citation passes; `open` is exempt from rule 2; the link is an exact test-ID string, so renaming or moving a test creates a new evidence identity and needs a manual review |
| C-37 | A dynamic sanitizer is accepted as an evidence channel only together with its output and the way the run ended | `schemas/sanitizer-run.schema.json`: `tool` (asan/ubsan/tsan/msan/lsan), `build_flags`, `command`, `output` + `output_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, optional `version`; `evidence[].sanitizer_runs` is valid on `kind=test` only; L1 checks the shape, the tool and status enums, the sha256 and ISO dates; L2 verifies the output hash, requires `finished_at` on the evidence date, `exit_code=0` and `status=completed` for a non-open claim, and rejects a "clean" record (`completed` + exit 0) whose output carries a finding line (`ERROR`/`WARNING: …Sanitizer:`, `SUMMARY: …Sanitizer:`); a recoverable UBSan `runtime error:` is deliberately not counted as a finding line | `schemas/sanitizer-run.schema.json`; `schemas/claim-ledger.schema.json`; `tools/claim_lint.py`; `evals/linter/cases/sanitizer-*.yaml` (7 cases); `spec/pilots/craft-i18n/claims.yaml` C-02; `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log`; `spec/pilots/craft-i18n/runs/asan-instrumentation-2026-11-07.md`; `spec/red-team/run_drills.py` (`sanitizer-findings-hidden`); `make verify` | craft-i18n at commit `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256`, nightly `1.101.0-nightly`, `-Zsanitizer=address`, `--target` keeps host artifacts separate; 26/26 tests, exit 0, 0 finding lines; the probe found `__asan_init` and `__asan_report_load*/store*` in the executed binary | tested | A sanitizer can disprove a claim but cannot prove the absence of a defect: a clean run means "nothing fired in this corpus with this instrumentation"; std is not instrumented; L2 trusts `build_flags` and does not prove instrumentation (only the separate probe does); recoverable UBSan is deliberately not matched; the corpus does not prove that the tests exercise the claim itself; a consistent forgery of the record and its output, and re-dating, remain (C-13) |
| C-38 | An independent row-grammar model agrees with `read_catalog` over a declared bounded space | `crosscheck/c02-row-model`: the model is written from `docs/catalog-format.md`, not translated from `catalog.rs`; the generator enumerates 10×30×25 single rows, arities 0–4, every pair of 19 rule-shaped lines and every triple of 11, 7×7×3 plural cases and five BOM/CRLF wrappers; the comparison is accepted rows `(line, context, source, translation)` and rejected line numbers, not the problem text; the binary aborts above 100,000 inputs or 256 bytes per input | `crosscheck/c02-row-model/src/model.rs`; `crosscheck/c02-row-model/src/main.rs`; `spec/proofs/c02-bound-2026-11-07.md`; `spec/proofs/runs/c02-crosscheck-2026-11-07.json`; `spec/pilots/craft-i18n/claims.yaml` C-02; `make crosscheck-c02` | craft-i18n at commit `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256`; 69,430 unique inputs, 11,142 accepted rows, 63,364 inputs with a rejected line, 0 divergences; record `completed`, exit 0 | tested | Agreement only within the vocabulary: arbitrary Unicode, long lines and catalogs of more than three rows are not exhausted; model and implementation share an author, so a shared misreading of the format is invisible; it is a differential check, not an equivalence proof; `check_tree`, discovery and locale validation are outside the model; `forms` ∈ {1,2,3}; duplicate detection is compared on catalogs of at most three rows; the target is pinned by `TARGET`, and a change after the pin is caught by `claim_lint` L2, not by the cross-check |
| C-39 | The bounded space is sensitive to every named model rule: 22 mutants are caught | `--mutants` runs the whole space 22 times, disabling one rule at a time (column count, empty fields, duplicate key, escapes, reserved contexts, placeholders, `…`, template, plural, control chars, BOM, CR, `@id`, line numbers, comments); a mutant with no divergence exits 1 | `crosscheck/c02-row-model/src/model.rs` (`Ruleset`); `crosscheck/c02-row-model/src/main.rs`; `spec/proofs/c02-bound-2026-11-07.md`; `spec/proofs/runs/c02-mutants-2026-11-07.json`; `make crosscheck-c02-mutants` | The same pin and the same 69,430-input space; 22/22 caught; record `completed`, exit 0 | tested | The mutants are known and hand-written; a high score is sensitivity to these edits, not completeness; caught means at least one divergence, not that the rule is covered on every input; the target pin and the authorship limits of C-38 apply |
| C-40 | A static-analysis finding does not disappear: the run record and its triage bind the engine, rules, commit, SARIF, report and one decision per finding | `schemas/static-analysis-run.schema.json`: `tool`, `command`, `rules{name,source,sha256}`, `target_commit`, `output` (SARIF) + `output_sha256`, `report` + `report_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, optional `cells`, `triage`, and a mandatory `anchor` (C-41); dispositions `covered`/`new` (a cell, detector and `path#MUT-ID` fixture are required) and `not-a-bug`/`out-of-scope` (a reason is required). L1 checks the shape and vocabulary; L2 hashes the rules and both outputs, requires `finished_at` on the evidence date, `exit_code=0` and `status=completed` for a non-open claim, checks `report.format`, that `output_sha256` is among `report.inputs[].sha256`, that the named engine has `runs>0`, that `summary.unmapped` and `summary.fixture_inputs` are 0, the `report.findings[].id` ↔ `triage[].finding` bijection, that every routed cell/detector/fixture resolves in the `cells` registry, and recomputes the anchor's canonical bytes and verifies the SSH signature against `allowed_signers` (C-41); L4 requires a record for `static-refinement` | `schemas/static-analysis-run.schema.json`; `schemas/claim-ledger.schema.json`; `tools/claim_lint.py`; `tools/sarif_evidence.py` (`aliases`, `--path-root`); `spec/sarif/adapters.yaml`; `spec/static-analysis/rules/ci-supply-chain-2026-11-07.yml`; `spec/static-analysis/rules/bandit-builtin-2026-11-08.yaml`; `spec/static-analysis/runs/`; `spec/static-analysis/README.md`; `spec/pilots/craft-i18n/claims.yaml` C-09; `spec/pilots/rbac_pg/analysis-claims.yaml` C-40; `spec/pilots/rbac_pg/triage_2026-11-08.py`; `spec/pilots/dev-sec-skills/` (C-01, CELL-001, D-PINNED-ACTIONS, MUT-001); `spec/anchor/` (C-41); `evals/linter/cases/static-analysis-*.yaml` (20 cases); `make verify` | Semgrep OSS 1.184.0 at `5c5c554` with three authored rules; 5 findings, 0 unmapped, 0 fixtures, 0 duplicates, exit 0, `completed`; rules `d05187db…`, SARIF `3e32c249…`, report `6ed91da2…`; F-003/F-004 are `covered` through a cross-pilot route to the self-pilot registry (`spec/pilots/dev-sec-skills/cells.yaml`, CELL-001 / D-PINNED-ACTIONS / MUT-001), and F-001/F-002/F-005 are `out-of-scope` because the pilot taxonomy owns no supply-chain class; the self-pilot on the same channel: pre-fix run at `d0c25c2` — 3 findings, all `new` → CELL-001, fix `67d0aec`, post-fix run at `67d0aec` — 0 findings; SARIF `2b09702b…` / `b8073caf…`, reports `f631739f…` / `6e6d746b…`; rbac_pg: two per-engine runs on 2026-11-08 (`d978609`) — Bandit 1.9.4, 63 findings, and Semgrep 1.184.0, 186 findings; SARIF `e59fa280…` / `a850a750…`, reports `8185cf35…` / `036733d7…`, digests `ad5199da…` / `5f1a53f6…`; all 249 entries are `not-a-bug`, 0 cells; `spec/pilots/rbac_pg/analysis-claims.yaml`, anchors `rbac-pg-bandit-2026-11-08` / `rbac-pg-semgrep-2026-11-08` | tested | One engine and one run; the rules are text rules (`generic` + regex), not data flow, and not the `p/ci` benchmark, so a different rule set yields a different queue; `new` was first exercised on a real self-pilot run (3 findings → CELL-001 → fix `67d0aec`); `covered` is no longer synthetic: craft-i18n F-003/F-004 are routed to the self-pilot, and a read-only D-PINNED-ACTIONS run over the craft-i18n workflow directory fails on `ci.yml:17` and `sonarcloud.yml:20` at `5c5c554`; the route crosses pilots — the detector belongs to the self-pilot and is not wired into craft-i18n's CI; `out-of-scope` is a taxonomy boundary, not a claim that the finding is harmless; Semgrep Registry rules are not vendored because of their licence, so a URL source is not re-hashed; engine and rules drift between versions; the first two pilots stay read-only, so a detector and fixture were added only in the self-pilot (`spec/pilots/dev-sec-skills/`); the C-41 anchor catches an edit after signing, but the key holder, replacement of `allowed_signers` plus re-signing, and re-dating with a new signature remain (C-13); in rbac_pg none of the 249 findings is routed, because the pilot registry owns neither `invalid-or-injected-input` nor `exposed-secret-or-weak-crypto` — a real injection would be `out-of-scope`, and `not-a-bug` says only that in this harness no external data reaches the cited statement; the triage reasons were read from the source at `d978609` and do not prove safety; the 2026-11-07 signing key was lost, so the 2026-11-08 records are signed by a new key, which does not prove when they were written (C-13) |
| C-41 | Every new evidence record carries an external anchor for its channel: an SSH signature over the record's canonical bytes | `tools/anchor_subject.py` builds canonical JSON (sorted keys, compact separators, trailing newline) for three channels: static-analysis — `tool`, `version`, `command`, `rules{name,source,sha256}`, `target_commit`, `output_sha256`, `report_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, `cells` (the registry a `covered` entry resolves against) and the whole `triage` list; run_record — `runner`, `command`, `commit`, `exit_code`, timestamps, `log_sha256`, `artifact_sha256`, `tests_run`, `tests_passed`; sanitizer — `tool`, `version`, `build_flags`, `command`, `exit_code`, timestamps, `output_sha256`, `status`; `tools/anchor_run.py keygen\|create\|verify --channel {static-analysis,run-record,sanitizer}` uses `ssh-keygen -Y sign/verify` (ed25519) under the channel's namespace; `anchor` is mandatory in `static_analysis_runs[]`, `run_record` and `sanitizer_runs[]` (L1 checks fields, types and the channel namespace), L2 recomputes the bytes, hashes subject and signature, requires subject == the record's canonical bytes and calls `ssh-keygen -Y verify` against the committed `allowed_signers`; the anchor is checked before the output or log paths, so a URL does not bypass it | `tools/anchor_subject.py`; `tools/anchor_run.py`; `schemas/static-analysis-run.schema.json`; `schemas/run-record.schema.json`; `schemas/sanitizer-run.schema.json`; `tools/claim_lint.py` (`check_anchor_shape`, `_check_anchor`); `spec/anchor/` (allowed_signers + 16 subjects + 16 `.sig` + a rotation README); `spec/pilots/dev-sec-skills/claims.yaml` C-01 static 0/1 + run_record 0, C-02 run_record 0; `spec/pilots/craft-i18n/claims.yaml` C-09 static 0, C-01…C-07 run_record (8) + C-02 sanitizer; `evals/linter/cases/static-analysis-anchor-{missing,tampered,bad-signature,unknown-signer}.yaml`, `evals/linter/cases/run-record-anchor-{missing,tampered}.yaml`, `evals/linter/cases/sanitizer-anchor-tampered.yaml` (6 cases); `spec/red-team/run_drills.py` `forge-anchored-record`, `forge-anchored-test-record`; `make verify`; `make red-team` | 16 real anchors and 7 synthetic cases; `anchor verified` for all 16 (5 static, 10 run_record, 1 sanitizer); editing `version`/`runner` after signing yields an L2 error "anchor subject does not describe this record"; replacing `.sig` yields an L2 error; a missing `anchor` yields an L1 error; a foreign namespace yields an L1/L2 error; a genuine signature from an identity outside `allowed_signers` yields an L2 error; both forge drills are blocked; `evals/linter` 77/77; `red-team` 18/18 (17 blocked, 1 allowed) | tested | The private key stays outside the repository (`/tmp/opencode/dev-sec-skills-anchor-2026-11-08/key`; the 2026-11-07 key was lost with `/tmp/opencode`), so a forger cannot re-sign; but the key holder can re-sign any edit, and replacing `allowed_signers` plus a new signature defeats everything; there is no transparency log, timestamping or key revocation; the anchor covers output hashes but not the paths themselves or `rules.source`; proof and review records are not anchored; without `ssh-keygen` a non-open claim gets an error and an open one gets info; 10 of the 16 records (9 run_record + 1 sanitizer) were signed retroactively on 2026-11-08, so the signature proves the record has not changed since signing, not that the run happened on 2026-11-07; losing the key makes re-signing old records impossible (they stay valid) and new records use a new signer |


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

A narrow variant is implemented for static-analysis records (C-41): an offline
SSH signature over the record's canonical bytes, with the public key in
`spec/anchor/allowed_signers` and the private key outside the
repository. It does not close C-13: the key holder can re-sign, and replacing
`allowed_signers` plus a new signature defeats the check.

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
  fixture and one documented exemption; a 9-claim ledger (C-19; C-09 is
  `static-refinement` with a recorded static-analysis run).
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
- Fuzzing (V2-17): `tools/fuzz_run.py` — seed corpus, random mutations with a fixed
  seed, OR-ed oracle rules, a budget, and a record shaped by
  `schemas/fuzz-run.schema.json`; the recorded `claim_lint` run (155 executions,
  seed 20261107) is `clean`, and `make fuzz-claim-lint` reproduces the digest. 5 eval
  cases.
- Finding triage (V2-18): `tools/fuzz_triage.py` requires exactly one entry per finding —
  `covered` / `new` with a cell, a detector and a fixture, or `not-a-bug` with a reason;
  the cell and detector resolve in the registry and the fixture in the mutations file.
  13 eval cases; the recorded run has no findings, so its triage is empty and that is the
  only accepted empty case.
- Coverage (V2-20): `tools/coverage_report.py` — CV1 a dangling citation (always an
  error), CV2 unmapped symbols, CV3 stale claims, CV4 detectors without a fixture;
  mapping is file-level and symbol extraction is narrow. 14 eval cases, `make coverage`
  in `make verify`, snapshots in `spec/coverage/`: `rbac_pg` 67/80 mapped,
  `craft-i18n` 26/26, 0 stale and 0 detectors without a fixture.
- Diff coverage (V2-07): `tools/diff_coverage.py` checks only choke points declared
  in `enforced_at`; DC1/DC2 a changed path or symbol without a non-open claim,
  DC3 an unlocatable declaration (always an error), DC4/DC5 explicit infos about an
  empty range and a registry with no declarations. 19 eval cases, snapshots in
  `spec/diff-coverage/`: `rbac_pg` `v1.3.1..HEAD` 2/2 mapped, `craft-i18n`
  `f0dd77b^..f0dd77b` 2/2 mapped. The gate is outside `make verify`: it needs a
  base ref; the PR-gate template is `ci/diff-coverage.yml`, and the targets are
  `make diff-coverage` and `make diff-coverage-record`.
- Choke-point extraction (V2-22): `tools/choke_points.py` finds structural
  candidates in ordinary code (Python `ast`; Rust/SQL masking lexers for comments,
  strings and dollar quotes) and maps them to cell classes through
  `spec/choke-points/rules.yaml`. Rules are ordered and the first match wins; a
  candidate with no rule is `unclassified`, not `other`. Measured 2026-11-07:
  `rbac_pg` 1585 definitions → 1413 candidates, 867 classified / 546 unclassified
  (38.6 %); `craft-i18n` 128 → 64, 47 / 17 (26.6 %); both 914/1477 = 61.9 %
  classified. 14 eval cases; snapshots in `spec/choke-points/`; targets
  `make choke-points` and `make choke-points-record`. The CP1 threshold is not in
  `make verify` until the noise is reduced.
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
- [x] V2-07. Diff coverage: changed choke-point paths and symbols must map to a claim: `tools/diff_coverage.py` (DC1 path, DC2 symbol, DC3 an unlocatable declaration — always an error, DC4 an empty range, DC5 a registry with no declarations), 19 eval cases, `ci/diff-coverage.yml`. Measured 2026-11-07: `rbac_pg` `v1.3.1..HEAD` — 110 files, 1 path and 1 symbol, 2/2 mapped; `craft-i18n` `f0dd77b^..f0dd77b` — 2/2 mapped. The gate is not in `make verify`: it needs a base ref; `make diff-coverage` and `make diff-coverage-record` are separate targets.
- [x] V2-08. `make verify` as the single local entry point for all static gates: evals, the seed registry, both pilot registries with their claim ledgers, the ledgers themselves, and the status diffs (`Makefile`). Mutation runs are separate: `make mutations` (PostgreSQL stand), `make mutations-i18n` (cargo), `make mutations-all`.
- [x] V2-34. Evidence-to-claim relevance: L6 in `claim_lint` requires `shared_tests: [{id, reason}]` for a test cited by two claims and rejects a non-open claim whose every test is borrowed, even when the sharing is declared; L1 checks the field's shape and the schema is updated. 6 eval cases (`shared-*`), the shared test `each_bad_row_is_one_problem` is declared in C-02 and C-03; the red-team drill `borrow-another-claims-evidence` is now blocked, and `borrow-and-declare-sharing` is added and also blocked. Residual: the test's assertions are not compared with the claim's wording; one own-but-irrelevant citation passes. Re-dating remains the C-13 gap.
- [x] V2-35. Sanitizer as an evidence channel: `schemas/sanitizer-run.schema.json` and `evidence[].sanitizer_runs` on `kind=test` only; L1 checks the shape (tool, flags, command, output, hash, exit code, ISO dates, status), L2 the output hash, the `finished_at` date, `status=completed`/`exit_code=0` for a non-open claim, and the contradiction between a "clean" record and a finding line in its own output. 7 eval cases (`sanitizer-*`); a real ASan run of craft-i18n on nightly 1.101.0: 26/26 tests, exit 0, 0 finding lines, log `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log`, probe `asan-instrumentation-2026-11-07.md` (`__asan_init` found); red-team drill `sanitizer-findings-hidden` is blocked. C-02 stays `tested`: the sanitizer strengthens evidence but does not raise the status. Residual: a clean run does not prove the absence of a defect; std is not instrumented; L2 checks the record, not the binary; recoverable UBSan is not matched; re-dating and a consistent forgery remain (C-13).
- [x] V2-09. Negative controls in `evals/linter`: stub test (`fake-test-id`), re-dating (`run-record-date-mismatch`, `run-record-log-hash`), unrelated commit (`unrelated-commit`: the commit resolves but the artifact changed after it — L2 compares the artifact with its blob at the commit) and empty model (`empty-claims`: an empty ledger is an L1 error, not a vacuous pass). 25/25 cases.
- [x] V2-10. `model-checked` and `proven` require tool output, not an artifact: `schemas/tool-output.schema.json` (`tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`; optional `version`, `commit`, `verdict`, `bound`), L1 checks the shape and commit/command agreement, L2 the output hash, the `finished_at` date and `exit_code=0` for a non-open claim, L4 the absence of `tool_output` for `model-checked`/`proven` and the absence of `bound` for `model-checked`. 7 eval cases; the pilots are unaffected (they use neither status).

**P1 — enforcement**

- [x] V2-11. `run_mutations.py` in CI for changed cells: `tools/mutation_plan.py` maps a target-repository diff to cells through `enforced_at`, detector `artifact`, fixture `artifact` and a changed registry, and writes a JSON plan; both runners accept `--plan` (an empty plan is a no-op, exit 0) and `--only-cell`; `--require-fixtures` fails when a changed cell has no fixture and no `mutation_exemption`; 13 eval cases, `ci/mutation-changed.yml`, `make mutation-plan`. Measured 2026-11-07: `rbac_pg` `v1.3.1..HEAD` — 25/25 fixtures, 0 uncovered; `craft-i18n` `f0dd77b^..f0dd77b` — 7/12 fixtures, 0 uncovered; the CI template has not run on a real runner.
- [x] V2-12. Assert that the predicted IDs failed, not just any test: both runners compare the failing set with `expect_failures` exactly (`spec/pilots/rbac_pg/mutations/run_mutations.py`, `spec/pilots/craft-i18n/mutations/run_mutations.py`).
- [x] V2-13. Negative control for `tested` in security: a recorded run with the guard disabled — closed by the mutation fixtures: every tested security detector has a predicted failing run or an exemption (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-14. Mutation fixtures for the remaining pilot detectors — 25 fixtures, 24 detectors with a fixture and 3 with a documented `mutation_exemption`; all 25 matched (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-15. `enforced_at`, `oracle`, `violation_response` fields in a cell: required when a detector has `kind: runtime-enforcement`; CL1 checks the shape. First cells — `rbac_pg` CELL-001 and `craft-i18n` CELL-003.
- [x] V2-16. A `runtime-enforcement` evidence kind with a mandatory negative test: `negative_test` on the detector, CL1 requires a non-empty ID, CL3 resolves it through `--suite-glob` (6 eval cases, including unresolved and unchecked), CL2 caps the cell status at `tested`.

**P2 — continuous loop**

- [x] V2-17. Fuzzing adapter: oracle, seed corpus, budget, fixed seed, run artifact: `tools/fuzz_run.py`, `schemas/fuzz-run.schema.json`, rules `exit:N`, `exit-not-in:`, `stdout-contains:`, `stderr-contains:`, `timeout`; `executions_digest` reproduces for the same corpus and seed. The recorded `claim_lint` run — 5 seed ledgers, 150 mutations, 155 executions, seed 20261107, `clean`; 5 eval cases; `make fuzz-claim-lint` compares the digest.
- [x] V2-18. Triage fuzzer findings → cell + detector + fixture: `tools/fuzz_triage.py` (T1–T4), `schemas/fuzz-triage.schema.json`, 13 eval cases; `make check-fuzz-triage` runs in `make verify`. The recorded run is clean, so the triage is empty; injecting a finding into a copy of the record makes the gate exit 1.
- [x] V2-19. Scheduled fuzzing that does not block merges: `.github/workflows/fuzz-nightly.yml` runs on cron `30 2 * * *` and `workflow_dispatch`, never on `push`/`pull_request`; it replays `spec/fuzz/runs/claim-lint-2026-11-07.json` through `make fuzz-claim-lint` and fails when `executions_digest` moves; the artifact `fuzz-record-<run_id>` carries the record and findings for 90 days. First run: [42394278295](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42394278295), 2026-11-07, commit `3110214`, success, digest `93e1af3183658aa6…`, seed 20261107, 155 executions, 0 findings; the downloaded artifact was compared locally. A second dispatch on `4dd83be`: [42414910152](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42414910152), 2026-11-07T21:14Z, success, the recorded and replayed digests matched (`93e1af3183658aa6`), 155 executions, 0 findings. The nightly schedule fired for the first time: [42466635404](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42466635404), event `schedule`, 2026-11-08T09:18:42Z→09:19:01Z, commit `7bf8192`, success, recorded and replayed digests matched (`93e1af3183658aa6`), seed 20261107, 155 executions, 0 findings; the downloaded artifact is committed as `spec/fuzz/runs/claim-lint-2026-11-08-schedule.json` (sha256 `8ca3fcb9…`). Limits: the declared cron is `02:30Z` but the job started at `09:18:42Z` — GitHub delays scheduled runs by hours, so "nightly" does not guarantee a time, and a delayed or skipped run is noticed by nobody because nothing alerts; the committed artifact is downloaded CI output, not a local run, and it is not anchored (C-41 covers three evidence channels and a fuzz record is not one of them); the replay proves determinism and input integrity, not new-bug discovery; the live GitHub artifact expires after 90 days and is not an external anchor (C-13); a red run blocks no merge and notifies no one.
- [x] V2-20. Coverage report: unmapped symbols, stale claims, cells without a fixture: `tools/coverage_report.py` (CV1–CV4), 14 eval cases, `make coverage` in `make verify`, recorded snapshots in `spec/coverage/`. Measured 2026-11-07: `rbac_pg` 80 symbols, 67 mapped, 13 unmapped in two uncited suite files; `craft-i18n` 26/26; 0 stale claims and 0 detectors without a fixture in both.

**General-code track — beyond RBAC**

- [x] V2-21. Invariant catalogue outside databases and roles: input validation, authn/session, secrets, lifecycle, transactions — `spec/invariants/catalog.yaml` (5 categories × 3 invariants; statement, enforcement, failure mode, entry points, choke-point rule, seed cells, oracle, violation response, evidence kind, negative test, ≥2 bypasses, limitations), `schemas/invariant-catalog.schema.json`, `tools/invariant_catalog.py` (INV1–INV5: categories, shape, references, evidence, seed-cell coverage), 15 eval cases, `make invariants` in `make verify`, snapshot `spec/invariants/2026-11-07-coverage.json`. Measured 2026-11-07: 15 invariants, 5 categories, 9/12 seed cells referenced + 3 out_of_scope, 9/11 choke-point rules used (unused: `sql-rls`, `migration`), 0 errors; all 15 invariants are `open` — no detector exists, so the negative tests remain a specification.
- [x] V2-22. AST choke-point extractor for ordinary code and mapping to cell classes: `tools/choke_points.py` (Python `ast`, decorators join the span; Rust/SQL structural masking lexers; a SQL span covers a dollar-quoted body), `spec/choke-points/rules.yaml` (signals + ordered rules, `other` forbidden, unclassified is a rule gap, not a cell), 14 eval cases and integration in `tools/diff_coverage.py` (19/19 cases). Measured 2026-11-07: `rbac_pg` 1585 definitions, 1413 candidates, 867 classified / 546 unclassified (38.6 %); `craft-i18n` 128, 64, 47 / 17 (26.6 %); both 61.9 % classified. CP1 is not in `make verify`; `make choke-points` and `make choke-points-record` are separate targets, snapshots in `spec/choke-points/`.
- [x] V2-23. SARIF adapters for two or three engines as evidence sources: `tools/sarif_evidence.py` normalizes SARIF 2.1.0, resolves the engine by `tool.driver.name` and maps each result by rule ID through `spec/sarif/adapters.yaml` (ordered rules, first match wins); `unmapped` with a reason instead of `other`; `cell` is optional but must resolve and must match the cell's `failure_class`; deduplication and a stable digest; `--max-unmapped`, `--require-engines`, `--reject-fixtures`; `schemas/sarif-evidence.schema.json`; 20 eval cases; `make sarif` / `make sarif-record`. Measured 2026-11-07 on authored fixtures (regenerated 2026-11-08 after the mismatched cell mappings were removed): 3 engines, 7 findings, 0 unmapped, 1 duplicate, 0 with a cell, digest `caf2a4f9fe24ba42`; at the time of V2-23 no real engine run existed, and the fixtures are marked `properties.dev-sec-skills/fixture = true`; later Bandit 1.9.4 + Semgrep 1.184.0 produced a real two-engine report (C-08).
- [x] V2-24. A second pilot on a non-RBAC codebase (web service or CLI): `craft-i18n`, a Rust crate that checks translation catalogs; 14 cells, 13 `tested` / 1 `open`, CL1–CL6 clean, 12/13 detectors with a mutation fixture, 8 claims (`spec/pilots/craft-i18n/`).
- [x] V2-25. The taxonomy was checked on a non-RBAC pilot; the `unroutable` share is measurable through an escape hatch: `taxonomy_class` or `failure_mode` = `other` with a mandatory `routing_note`, `tools/unroutable.py`, and a `--max-share 0` gate in `make verify`. Measured 0/43 = 0.0 %; before the hatch, 0 was structural (`product-trials.en.md` §2.1).
- [x] V2-26. Exit criterion met: two pilots (`rbac_pg`, `craft-i18n`), U measured (0/43), N and U fixed before the first product run, 21/24 security detectors with a fixture.

**Formal-model boundary**

- [x] V2-27. Record in `guard-grammar.md`: L2 is a model diff plus a check that stable goals survive; theorem synthesis from code is not claimed.
- [x] V2-28. Bounded fallback for goal-survival checking: `tools/bounded_check.py` starts the tool in its own process group and kills it at `--timeout`; the `tool_output` record must carry `status` (`completed`/`unverified`/`failed`/`error`), `timed_out`, `bound_seconds` and `elapsed_seconds`; L1 rejects `timed_out` contradicting the status, L2 forbids `status != completed` from supporting a non-open claim; `evals/bounded-check/` 10/10 plus 5 new linter cases (linter 40/40); rules in guard-grammar §6.6.
- [x] V2-29. Proofs (`proven`) are event-driven: the trigger is a changed choke point or model, not every PR: `tools/proof_plan.py` reads a dependency manifest (`schemas/proof-manifest.schema.json`), compares it with `base..head` and prints `rerun`/`fresh` with a reason; gates `--require-fresh` (a re-run has not happened) and `--require-complete` (changed proof material is unclaimed), exit 2 on a broken manifest. `spec/proofs/manifest.yaml` is empty: no claim here is `proven`, and the planner says outright that an empty manifest makes `--require-fresh` vacuous. Cases live in `evals/proof-plan/`: 36/36; `evals/proof-plan/mutation_selftest.py` catches 8/8 planner mutations with a case named for the behaviour (`make proof-plan-selftest`, outside `verify`). Limits: synthetic repositories and a demo over the real range `a50fbda..HEAD`, no real proof was re-run; the manifest is the scope, not completeness; freshness compares `finished_at` with commit time rather than checking which checkout produced the record; `claim_lint` checks the record hash and no one checks the record's semantics.
- [x] V2-30. The slice's sync budget is measured as RERUN, not promised: the manifest declares 2 entries (P-01 agreement, P-02 mutants), 4 `depends_on` paths and 3 `model`/`encoding`/`tooling` paths; a full re-run of the slice on a warm cache is 0.953 s + 7.412 s = 8.365 s. Measured 2026-11-07: range `a3293ec..4f3e25c` (9 changed files, including the model) — 2 fresh / 0 rerun under `record-covers-change`; docs-only range `02be7ab~1..02be7ab` (5 files) — 0 rerun / 2 fresh; `--require-fresh` exit 0. A PR touching `crosscheck/c02-row-model/src/**`, `Cargo.toml`, `Cargo.lock` or `TARGET` requires 2 re-runs; a change to the target after the pin is invisible to the planner and is caught only by `claim_lint` L2. Residual: the manual model edit when the format changes is not measured; a cold build (~38 s) depends on the machine; the metric records re-run cost, not sync quality.

**Product-trial boundary**

- [x] V2-31. Fix the boundary in `spec/conveyor/product-trials.en.md`: entry criteria and the measurement protocol; numbers only after measurement.
- [x] V2-32. The threshold inputs were measured and recorded in `product-trials.en.md` §2.1 with artifacts: N = 87.5 % (21/24), U = 0.0 % (0/43), date 2026-11-07.
- [x] V2-36. Static analysis as an evidence channel with built-in triage: `schemas/static-analysis-run.schema.json` and `evidence[].static_analysis_runs` on `kind=static-analysis` only; L1 checks the shape and four dispositions, L2 the hashes of the rules/SARIF/report, `finished_at`, `completed`+exit 0, `report.format`, `output_sha256` among the report inputs, an engine with `runs>0`, zero `unmapped`/`fixture_inputs`, the triage/finding bijection and cell/detector/fixture resolution, and L4 requires a record for `static-refinement`. 17 eval cases (`static-analysis-*`), 20 including the C-41 anchor cases; a real Semgrep OSS 1.184.0 run over craft-i18n `5c5c554` with three authored MIT rules: 5 findings, 0 unmapped, 0 fixtures, exit 0, F-003/F-004 are real `covered` through the self-pilot, F-001/F-002/F-005 are `out-of-scope` (C-09); rules `d05187db…`, SARIF `3e32c249…`, report `6ed91da2…`. Semgrep Registry `p/ci` is not vendored because of the Rules License v1.0. Red-team drill `static-findings-hidden` is blocked. Residual: one engine and one run, `new` is real only in the self-pilot, `covered` is real only through the cross-pilot route of F-003/F-004 (the detector belongs to the self-pilot and is not in craft-i18n's CI), the rules are text rules and not a benchmark, a URL rule source is not re-hashed, and a consistent forgery and re-dating remain (C-13).
- [x] V2-37. External anchor for an evidence record (C-41): `tools/anchor_subject.py` defines the canonical bytes of three channels (static-analysis: engine, command, rule and both output hashes, commit, exit code, timestamps, status, `cells`, whole triage; run_record: runner, command, commit, exit code, timestamps, log and artifact hashes, counts; sanitizer: tool, version, build_flags, command, exit code, timestamps, output hash, status), `tools/anchor_run.py keygen|create|verify --channel` signs and verifies them through `ssh-keygen -Y sign/verify` (ed25519) under the channel namespace; `anchor` is mandatory in `static_analysis_runs[]`, `run_record` and `sanitizer_runs[]`, and L2 recomputes the bytes, hashes subject and signature and checks the signature against the committed `spec/anchor/allowed_signers`. The private key is outside the repository. 13 anchors: 3 static (C-01 runs 0/1, C-09 run 0), 9 run_record (craft-i18n C-01…C-07, including two on C-02, and self-pilot C-01) and 1 sanitizer (craft-i18n C-02 ASan); 10 of them are a 2026-11-08 backfill over 2026-11-07 records, so the signature proves immutability after signing, not the run date. On 2026-11-08 `cells` was added to the signed fields, so static C-01/0 and C-09/0 were re-signed while static C-01/1 was unchanged (no `cells`). 7 negative linter cases (`static-analysis-anchor-{missing,tampered,bad-signature}`, `run-record-anchor-{missing,tampered}`, `sanitizer-anchor-tampered`, `static-analysis-anchor-unknown-signer`), a rotation README in `spec/anchor/`, red-team drills `forge-anchored-record` and `forge-anchored-test-record` — blocked (18/18). The anchor directory moved from `spec/static-analysis/anchor/` to `spec/anchor/`: the subject carries no path, so the signatures stayed valid. Residual: the key holder can re-sign, replacing `allowed_signers` plus a new signature bypasses the check, there is no transparency log/timestamping/revocation, and proof/review records are not anchored (C-13 stays open).
- [ ] V2-33. Fill the boundary checklist when the first product sprint opens; product runs before that do not count as statistics.

- [x] V2-38. Bootstrap path for a foreign repository: `tools/bootstrap.py` is a deterministic, idempotent planner/generator (`--target`, `--name`, `--suite-glob`, `--ledger`, `--registry`, `--with-ci`, `--with-anchor`, `--source`, `--signer`, `--anchor-dir`, `--allowed-signers`, `--force`, `--dry-run`); it vendors `tools/{claim_lint,cell_lint,status_diff,anchor_subject,anchor_run}.py`, `styles/` and `schemas/` without their README files, and `spec/conveyor/cell-registry.schema.json`, and writes `tools/dev-sec-skills.VERSION` (source commit, dirty flag, sha256 of each file); it creates `open` registry and ledger templates (one claim with `evidence: []`, one cell with no detectors), renders `.github/workflows/{claim,cell}-lint.yml` from `ci/` with `FIRST_RELEASE=1`, and creates or reuses an ed25519 key outside the target while committing only `allowed_signers`. `--force` refreshes vendored files and CI, but never overwrites the registry or the ledger. Self-check: `evals/bootstrap/run_evals.py` (4/4: file creation and VERSION hashes, idempotency, drift and recovery, green open gates, the path to `tested` with an anchor, refusal to overwrite the ledger, failure on a changed signed field, `status_diff` without new evidence, refusal of a target inside the source and of a key inside the target), the `D-BOOTSTRAP` detector in the self-pilot (C-02), and the recorded log and anchor in `spec/pilots/dev-sec-skills/runs/`; documentation in `docs/onboarding.md`/`docs/onboarding.en.md`. Residual: the eval is synthetic (one temporary git repository, stdlib runner, Linux); the CI templates keep the mutable `actions/checkout@v4`/`setup-python@v5` refs and need pinning before the gate is enabled; the path was exercised on one runner type; C-13 (the key holder can re-sign, replacing `allowed_signers`, no transparency log/timestamping/revocation) stays open; the bootstrap does not check that the test exercises the statement of the claim.


- [x] V2-39. Append-only verdict journal (C-13): `tools/verdict_journal.py verify|append` — `spec/journal/verdicts.jsonl` (one canonical JSON line per verdict: `seq`, `date`, `ledger`, `claim`, `status`, `evidence` = sorted sha256 digests of the identity `(kind, commit, artifact, command, tests, date)`, `prev`, `hash`) and a head `spec/journal/head.json` + `.sig` (namespace `dev-sec-skills-verdict-journal`; fields `seq`, `head`, `journal_sha256`, `generated`, `signer`, `namespace`, `ledgers` with the exact bytes of each ledger). Gate J1 — the chain (`seq` 1..N, `prev`, recomputed `hash`, status vocabulary); J2 — the journal's last word matches the ledger (status, evidence set, `retired` tombstone, unknown ledger); J3 — the journal at `--git-ref` is a byte prefix of the working file (deletion, truncation, rewrite); J4 — the head is canonical, names the last entry and the file hash, names the current bytes of every ledger, and verifies with `ssh-keygen -Y verify` against `spec/anchor/allowed_signers`. Append is atomic (tmp + `os.replace`, the temporary head is signed before the swap) and refuses a broken chain, head or history; the signer must be listed in `allowed_signers` with the same key. Backfill: 11 entries (2 self-pilot + 9 craft-i18n), head seq 11; entry 12 is C-42 itself, so the head is seq 12, signer `dev-sec-skills-anchor-2026-11-08`. `evals/journal/run_evals.py` — 14 cases (append/verify, idempotence, status and evidence without an entry, a prose edit with head re-sign, retired, edited/dropped entry, truncated history, non-canonical and rewritten head, foreign signer, append refusals); detector `D-JOURNAL` in the self-pilot; `make journal`, `make journal-append`; README `spec/journal/README.md` with the threat model; red-team drills `drop-a-journal-entry` (blocked) and `rewrite-journal-and-resign` (allowed, a recorded hole), 20/20. Remainder: the external `../rbac_pg/docs/claims.yaml` is outside the journal; proof/review records are not anchored; the key holder, replacement of `allowed_signers` with re-signing and a git history rewrite bypass everything; there is no transparency log, timestamping or key revocation; the entry date is the journaling day, so the backfill does not prove the past; bootstrap does not vendor the journal.

- [x] V2-40. A push CI gate for the self-sufficient checks, and the repository handover: `.github/workflows/verify.yml` — `push` to `main` and `workflow_dispatch`, `permissions: contents: read`, concurrency per ref, a 20-minute timeout, checkout with `fetch-depth: 0` (J3 compares the journal with a commit, L2 resolves the commits named by evidence), setup-python 3.12, PyYAML, actions pinned to commit SHAs, one `make verify-ci` step; the new target `verify-ci` = `verify-repo verify-self status-pilot2 journal unroutable invariants`. The pilot gates (`verify-pilot`, `verify-pilot2`, `coverage`, `red-team`, `verify-all`) stay local: `../rbac_pg` has no remote and `../astraoffice/craft-i18n` needs a deploy key. First run: [42489712970](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42489712970), 2026-11-08, commit `11caf2a`, success, 34 s. The journal key moved from `/tmp/opencode` to `~/.config/dev-sec-skills/anchor/key` (mode 600, outside git), so the default `JOURNAL_KEY` now matches reality: `make journal-append` → "no changes to append (12 entries)". `docs/handover.md`/`.en.md`: environment and sibling checkouts with their commits, the gates, the change ritual, keys and rotation, the map of open holes, the first week. Remainder: CI does not cover the pilots, coverage or red-team; Vale is not installed in CI, so L5 degrades to `--no-vale` and the 72 pre-existing self-pilot warnings have no threshold; the external `../rbac_pg/docs/claims.yaml` is outside the journal; CI holds no secrets because `verify` only checks signatures, it does not create them.

- [x] V2-41. `claim_lint` findings reach the diff, not only the log: `--format github` prints `::error`/`::warning` workflow commands with `file`, `line` and `title`; the location is the finding's own `file:line` (L5), else the claim's block in the ledger (`claim_lines` through `yaml.compose`, the 1-based `start_mark`), else the ledger itself with no line; properties are escaped (`%`→`%25`, `:`→`%3A`, `,`→`%2C`, `\r`/`\n` per the runner's rules). The default threshold is `error` (`--annotations warning` adds warnings), because the self-pilot carries 72 L5 warnings that would bury the diff. The text format did not change. `evals/claim-format/` — 8/8 cases (block location, warning suppression, escaping, a JSON ledger with no line, a finding with no claim, the text-output regression, unit checks for the escapers and `claim_lines`); D-CLAIM-FORMAT (`test_claim_format_eval_cases_pass`) runs the eval as one test ID. The `ci/claim-lint.yml` template for target repositories now calls the linter with `--format github`, so findings surface on the changed lines of a pull request. Remainder: GitHub shows the first ten annotations per step and the rest only in the log; JSON ledgers get no `line` (PyYAML does not compose JSON); L1–L4/L6 carry no location of their own and point at the claim block, not the field; the output is not SARIF and is not uploaded to Code Scanning (the emitter is a separate increment).

## 13. Open questions and next evidence

1. **Pilot.** rbac_pg is chosen; the pilot registry is built (C-18): 29
   cells, 0 CL1/CL3/CL4 errors. All ten suites were re-run on a fresh stand on
   2026-11-06; 24 of 27 detectors have a mutation fixture and 3 more have a
   documented `mutation_exemption`; CL2 has no warnings. The second pilot
   `craft-i18n` (Rust, non-RBAC, non-database) was built on 2026-11-06:
   14 cells, 12/13 detectors with a fixture, 9 claims (C-09 is
   `static-refinement`), 0 errors; its open
   CELL-002 records a real gap with Unicode Cf characters. Still open: whether
   the claim ledger covers more than the FSTEC matrix. Without that,
   C-07…C-12 remain hypotheses.
2. **Verdict anchor.** The append-only journal with a signed head is
   implemented (V2-39) and closes silent rewriting of the past within one key
   holder. Still to choose: the external footing — Rekor/SCITT,
   in-toto+Sigstore, a transparency log or timestamping — otherwise the key
   holder and replacement of `allowed_signers` plus re-signing stay outside the
   threat model.
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

9. **A conveyor for ordinary software.** The skeleton (claim → mechanism →
   evidence → scope → status) is domain-agnostic: the `invariant-first-code`
   and `evidence-first-docs` skills already address general code correctness,
   and `cells.seed.yaml` reaches beyond databases and roles. The move is not a
   second conveyor but three changes: the taxonomy source (a business
   requirement catalogue — SLAs, calculation correctness, compatibility —
   instead of the FSTEC matrix), the verdict cost model (deep verification
   only where the risk justifies it, and every refusal to verify is itself a
   verdict with evidence), and the definition of a "minimally sufficient"
   security level as a risk-based decision rather than "what we had time for".
   The product risk register and threat model need evidence of their own;
   otherwise "sufficient" is indistinguishable from "not checked". No numbers
   are recorded: there are no product runs yet (V2-33). Do it after external
   feedback on the current conveyor, so it is visible which parts of the
   skeleton are reused.

## Appendix A. Relation to repository artifacts

| Artifact | Role in the concept |
| --- | --- |
| `skills/invariant-first-code/` | Cell content: invariant categories, enforcement points, fail-closed |
| `skills/negative-test-first/` | Detector fixtures and verifier self-checking |
| `skills/evidence-first-docs/` | Verdict format and status ladder |
| `schemas/claim-ledger.schema.json` | Prototype of the verdict registry |
| `tools/claim_lint.py` | Checks L1–L6 that `cell_lint` will reuse |
| `tools/cell_lint.py` | Checks CL1–CL6 over the cell registry |
| `tools/status_diff.py` | Ban on status escalation without new evidence |
| `tools/coverage_report.py` | CV1–CV4: dangling citations, unmapped symbols, stale claims, detectors without a fixture |
| `tools/invariant_catalog.py` | INV1–INV5: the five categories, shape, references, evidence and seed-cell coverage |
| `spec/invariants/` | Invariant catalogue outside databases and roles: 15 entries, 5 categories, out_of_scope and a coverage snapshot |
| `tools/bounded_check.py` | V2-28: a bounded run of an external tool; a timeout kills the process group and yields `unverified` |
| `schemas/tool-output.schema.json` | Machine-readable record of a run: `status`, `timed_out`, `bound_seconds`, output hash |
| `schemas/sanitizer-run.schema.json` | V2-35: sanitizer-run record: tool, instrumentation flags, command, output and its hash, exit code, status |
| `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log` | Recorded ASan run of craft-i18n: 26/26 tests, exit 0, no findings |
| `evals/bounded-check/` | Adversarial set for the supervisor: 10 cases, including process-group survival and the `claim_lint` link |
| `tools/sarif_evidence.py` | V2-23: SARIF 2.1.0 → normalized findings with a class, failure mode and optional cell; `unmapped` with a reason |
| `spec/sarif/` | Adapters for three engines, authored fixtures with explicit provenance, and a recorded report |
| `tools/anchor_subject.py`, `tools/anchor_run.py` | C-41: the canonical bytes of the three evidence channels and the `keygen`/`create`/`verify --channel` commands for the SSH anchor |
| `spec/anchor/` | C-41: the committed `allowed_signers`, the subject/signature pairs of 13 records across three channels, and a README on adding, retiring, rotating and losing a key; the private key is outside the repository |
| `tools/mutation_plan.py` | V2-11: diff → changed cells → selected mutation fixtures |
| `tools/proof_plan.py` | V2-29: diff → proofs that must be re-run; `--require-fresh` and `--require-complete` |
| `spec/proofs/` | Dependency manifest (P-01/P-02), the declared bound and the freshness rules: C-38/C-39 |
| `crosscheck/c02-row-model/` | Independent row-grammar model of craft-i18n plus a mutation harness: 22 named edits, a path dependency on the target |
| `spec/red-team/` | 18 attacks on the real pilot artifacts: 17 blocked, 1 recorded silent path (re-dating plus replacing the signer); borrowed evidence is closed by L6, hiding a finding line by L2 (C-37), forging a signed record by the anchor (C-41), including editing a signed run_record (L2) |
| `ci/mutation-changed.yml` | CI template: plan from the merge base, run only selected fixtures, skip on an empty plan |
| `.github/workflows/fuzz-nightly.yml` | V2-19: nightly replay of the recorded fuzz run; cron + dispatch, no push/PR, a 90-day artifact |
| `tools/diff_coverage.py` | DC1–DC5: a changed choke point must map to a non-open claim |
| `evals/linter/` | Example adversarial set for detectors |
| `evals/cell-lint/` | Adversarial set for `cell_lint` |
| `spec/conveyor/cell-registry.schema.json` | Machine-readable cell |
| `spec/pilots/rbac_pg/` | Pilot registry: 29 cells on a real repository |
| `spec/pilots/craft-i18n/` | Second pilot: 14 cells on a Rust crate, non-RBAC and non-database |
| `spec/coverage/` | CV1–CV4: method, measured numbers, limits, 2026-11-07 snapshots |
| `spec/diff-coverage/` | DC1–DC5: declarations, extractor, measured numbers, limits, 2026-11-07 snapshots |
| `spec/conveyor/guard-grammar.en.md` | Limits of L2 |
| `spec/conveyor/product-trials.en.md` | Product-trial boundary: entry criteria, metrics and measurement protocol (draft) |
| `Makefile` | `make verify` as the single entry point for static gates (V2-08); `make mutations` (PostgreSQL stand), `make mutations-i18n` (cargo) and `make mutations-all` for the mutation suites |

This document is not a certification, an audit, or a coverage promise. It
records intent, limits, and the next evidence.
