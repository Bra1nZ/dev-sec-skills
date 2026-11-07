# Single local entry point for every static gate (V2-08).
#
#   make verify        every gate that needs no external service
#   make verify-all    verify + both mutation batches (PostgreSQL stand and cargo)
#   make mutations     only the rbac_pg mutation suite (needs a built extension)
#   make mutations-i18n  only the craft-i18n mutation fixtures (needs cargo)
#
# Nothing here proves a property. A green run means the registries, ledgers,
# and evals are internally consistent; it is not a certificate.

PYTHON ?= python3

# Pilot registry lives in this repository; its artifacts live in the pilot.
PILOT_ROOT ?= ../rbac_pg
PILOT_REGISTRY ?= spec/pilots/rbac_pg/cells.yaml
PILOT_LEDGER ?= docs/claims.yaml
PILOT_SUITE_GLOB ?= setup/*.py

# Second pilot: a Rust crate, no database. Its claim ledger lives here, not in
# the target, so the target stays unmodified.
PILOT2_ROOT ?= ../astraoffice/craft-i18n
PILOT2_REGISTRY ?= spec/pilots/craft-i18n/cells.yaml
PILOT2_LEDGER ?= spec/pilots/craft-i18n/claims.yaml
PILOT2_SUITE_GLOB ?= crates/craft-i18n-tests/**/*.rs
PILOT2_MUTATION_TARGET_DIR ?= /tmp/opencode/craft-i18n-target

# C-02 bounded cross-check: an independent row-grammar model with a path
# dependency on the second pilot checkout. It needs that checkout and is a
# bounded model check, not a merge gate, so it is not in `verify`.
CARGO ?= cargo
C02_MANIFEST ?= crosscheck/c02-row-model/Cargo.toml
C02_TARGET_DIR ?= /tmp/opencode/c02-crosscheck-target

# Base ref for the status-escalation gates. HEAD compares the working tree
# against the last commit; CI uses the release tag instead.
BASE_REF ?= HEAD
# The pilot ledger postdates v1.3.1, so the first-release exemption is the
# honest state: there is no released base to escalate from. Remove this
# variable once a release contains docs/claims.yaml.
PILOT_LEDGER_FIRST_RELEASE ?= 1
PILOT_LEDGER_BASE_REF ?= v1.3.1

# Mutation runs need a live PostgreSQL with the extension installed.
MUTATION_DSN ?= postgresql://postgres@127.0.0.1:55434/postgres
MUTATION_SHAREDIR ?= /tmp/opencode/pgmut/usr/share/postgresql/15/extension

# Changed-cell selection (V2-11). This is a planner, not a runner: it prints
# the fixtures a diff selects and writes the JSON that `--plan` consumes.
MUTATION_PLAN_RBAC ?= /tmp/opencode/mutation-plan-rbac.json
MUTATION_PLAN_I18N ?= /tmp/opencode/mutation-plan-i18n.json

# Use Vale when it is installed, otherwise the built-in L5 scanner.
CLAIM_LINT_ARGS ?= $(shell command -v vale >/dev/null 2>&1 || echo --no-vale)

# Recorded fuzz run (V2-17). The replay target is not part of `verify`: it
# executes the target ~155 times (about a minute) to prove the digest
# reproduces, which is a manual, on-demand check rather than a merge gate.
FUZZ_RECORD ?= spec/fuzz/runs/claim-lint-2026-11-07.json
FUZZ_TRIAGE ?= spec/fuzz/triage/claim-lint-2026-11-07.yaml
FUZZ_CORPUS ?= spec/fuzz/corpus/claim-lint
FUZZ_SEED ?= 20261107
FUZZ_RUNS ?= 150
# Optional output directory for a CI run (V2-19). When set, the replay record
# and findings are copied there; the default keeps them in the temp dir.
FUZZ_OUT ?=

# Coverage measurement (V2-20). The record target writes the two JSON
# snapshots that back the evidence; plain `coverage` only prints, so a merge
# gate never rewrites a tracked artifact.
COVERAGE_RECORD_RBAC ?= spec/coverage/2026-11-07-rbac-pg.json
COVERAGE_RECORD_I18N ?= spec/coverage/2026-11-07-craft-i18n.json

# Diff coverage (V2-07). These are not part of `verify`: a merge gate needs a
# base ref, while `verify` compares the working tree against the last commit of
# this repository. The ranges below are fixed measurements, not PR ranges.
DIFF_BASE_RBAC ?= v1.3.1
DIFF_BASE_I18N ?= f0dd77b^
DIFF_HEAD_I18N ?= f0dd77b
DIFF_RECORD_RBAC ?= spec/diff-coverage/2026-11-07-rbac-pg.json
DIFF_RECORD_I18N ?= spec/diff-coverage/2026-11-07-craft-i18n.json

# Choke-point extraction (V2-22). The scan is a review queue, not a gate: the
# unclassified threshold stays unset until an agreed ceiling exists.
CHOKE_RULES ?= spec/choke-points/rules.yaml
CHOKE_SCHEMA ?= spec/conveyor/cell-registry.schema.json
CHOKE_RECORD_RBAC ?= spec/choke-points/2026-11-07-rbac-pg.json
CHOKE_RECORD_I18N ?= spec/choke-points/2026-11-07-craft-i18n.json

# Invariant catalogue (V2-21). A consistency gate, not a coverage claim: every
# entry is open until a detector cites it.
INVARIANT_CATALOG ?= spec/invariants/catalog.yaml
INVARIANT_CELLS ?= spec/conveyor/cells.seed.yaml
INVARIANT_RULES ?= spec/choke-points/rules.yaml
INVARIANT_SCHEMA ?= schemas/invariant-catalog.schema.json
INVARIANT_RECORD ?= spec/invariants/2026-11-07-coverage.json

# SARIF adapters (V2-23). The default target exercises the three AUTHORED
# fixtures; a real job points SARIF_INPUTS at engine output and adds
# SARIF_STRICT=--reject-fixtures.
SARIF_CONFIG ?= spec/sarif/adapters.yaml
SARIF_INPUTS ?= spec/sarif/fixtures
SARIF_STRICT ?=
SARIF_RECORD ?= spec/sarif/2026-11-07-report.json

# Proof planning (V2-29). Event-driven `proven`: a diff decides which proofs
# must be re-run. PROOF_BASE is the comparison ref; the target resolves the
# merge base, because a base-branch tip is not the fork point. The planner is
# informational here (no --require flags): a stale proof is reported, and the
# gates are opt-in for a repository that actually has proofs.
PROOF_MANIFEST ?= spec/proofs/manifest.yaml
PROOF_BASE ?= origin/main
PROOF_HEAD ?= HEAD

# Red-team drills. Synthetic evals check known violations; the drills attack the
# real craft-i18n ledger, its committed cargo log and the cell registry. They
# need that checkout and are a point-in-time audit, so they are not in `verify`.
RED_TEAM_RECORD ?= spec/red-team/2026-11-07-drills.json

.PHONY: verify verify-all verify-repo verify-pilot verify-pilot2 evals lint-seed \
        lint-pilot lint-pilot2 claims-pilot claims-pilot2 status-pilot \
        status-pilot2 unroutable coverage coverage-record diff-coverage \
        diff-coverage-record choke-points choke-points-record invariants \
        invariants-record sarif sarif-record mutation-plan mutations \
        mutations-i18n mutations-all check-fuzz-triage fuzz-claim-lint \
        proof-plan proof-plan-selftest crosscheck-c02 crosscheck-c02-mutants red-team red-team-record help

verify: verify-repo verify-pilot verify-pilot2 unroutable coverage invariants

verify-all: verify mutations-all

verify-repo: evals lint-seed check-fuzz-triage

verify-pilot: lint-pilot claims-pilot status-pilot

verify-pilot2: lint-pilot2 claims-pilot2 status-pilot2

evals:
	@echo "== evals: adversarial cases for the linters =="
	$(PYTHON) evals/cell-lint/run_evals.py
	$(PYTHON) evals/linter/run_evals.py
	$(PYTHON) evals/status-diff/run_evals.py
	$(PYTHON) evals/fuzz/run_evals.py
	$(PYTHON) evals/fuzz-triage/run_evals.py
	$(PYTHON) evals/coverage/run_evals.py
	$(PYTHON) evals/diff-coverage/run_evals.py
	$(PYTHON) evals/choke-points/run_evals.py
	$(PYTHON) evals/mutation-plan/run_evals.py
	$(PYTHON) evals/invariant-catalog/run_evals.py
	$(PYTHON) evals/sarif/run_evals.py
	$(PYTHON) evals/bounded-check/run_evals.py
	$(PYTHON) evals/proof-plan/run_evals.py

lint-seed:
	@echo "== CL1-CL6: seed registry =="
	@tmp=$$(mktemp --suffix=.yaml); trap 'rm -f "$$tmp"' EXIT; \
	if ! git show "$(BASE_REF):spec/conveyor/cells.seed.yaml" > "$$tmp" 2>/dev/null; then \
	  echo "error: no spec/conveyor/cells.seed.yaml at $(BASE_REF)" >&2; exit 1; \
	fi; \
	$(PYTHON) tools/cell_lint.py --base "$$tmp" spec/conveyor/cells.seed.yaml

lint-pilot:
	@echo "== CL1-CL6: pilot registry (with the pilot claim ledger) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -f "$(PILOT_ROOT)/$(PILOT_LEDGER)" || { echo "error: pilot ledger not found: $(PILOT_ROOT)/$(PILOT_LEDGER)" >&2; exit 1; }
	@tmp=$$(mktemp --suffix=.yaml); trap 'rm -f "$$tmp"' EXIT; \
	if ! git show "$(BASE_REF):$(PILOT_REGISTRY)" > "$$tmp" 2>/dev/null; then \
	  echo "error: no $(PILOT_REGISTRY) at $(BASE_REF)" >&2; exit 1; \
	fi; \
	$(PYTHON) tools/cell_lint.py \
	  --root "$(PILOT_ROOT)" \
	  --ledger "$(PILOT_ROOT)/$(PILOT_LEDGER)" \
	  --suite-glob "$(PILOT_SUITE_GLOB)" \
	  --base "$$tmp" \
	  "$(PILOT_REGISTRY)"

claims-pilot:
	@echo "== L1-L6: pilot claim ledger =="
	$(PYTHON) tools/claim_lint.py \
	  --root "$(PILOT_ROOT)" \
	  --suite-glob "$(PILOT_SUITE_GLOB)" \
	  $(CLAIM_LINT_ARGS) \
	  "$(PILOT_ROOT)/$(PILOT_LEDGER)"

status-pilot:
	@echo "== status diff: pilot ledger against $(PILOT_LEDGER_BASE_REF) =="
	@set -e; \
	args="--repo $(PILOT_ROOT) --ledger $(PILOT_LEDGER) --git-ref $(PILOT_LEDGER_BASE_REF)"; \
	if [ "$(PILOT_LEDGER_FIRST_RELEASE)" = "1" ]; then \
	  args="$$args --first-release"; \
	  echo "note: first-release exemption: $(PILOT_LEDGER) is newer than $(PILOT_LEDGER_BASE_REF)"; \
	fi; \
	$(PYTHON) tools/status_diff.py $$args

invariants:
	@echo "== INV1-INV5: invariant catalogue outside databases and roles (V2-21) =="
	$(PYTHON) tools/invariant_catalog.py \
	  --catalog "$(INVARIANT_CATALOG)" \
	  --cells "$(INVARIANT_CELLS)" \
	  --rules "$(INVARIANT_RULES)" \
	  --schema "$(INVARIANT_SCHEMA)"

invariants-record:
	@echo "== INV1-INV5: record the invariant coverage snapshot (V2-21) =="
	$(PYTHON) tools/invariant_catalog.py \
	  --catalog "$(INVARIANT_CATALOG)" \
	  --cells "$(INVARIANT_CELLS)" \
	  --rules "$(INVARIANT_RULES)" \
	  --schema "$(INVARIANT_SCHEMA)" \
	  --json "$(INVARIANT_RECORD)"

sarif:
	@echo "== SARIF adapters: engine + rule -> taxonomy finding (V2-23) =="
	$(PYTHON) tools/sarif_evidence.py \
	  --config "$(SARIF_CONFIG)" \
	  --root . \
	  --max-unmapped 0 --require-engines 3 $(SARIF_STRICT) \
	  --list \
	  $(SARIF_INPUTS)

sarif-record:
	@echo "== SARIF adapters: record the fixture report (V2-23) =="
	$(PYTHON) tools/sarif_evidence.py \
	  --config "$(SARIF_CONFIG)" \
	  --root . \
	  --max-unmapped 0 --require-engines 3 \
	  --json "$(SARIF_RECORD)" \
	  $(SARIF_INPUTS)

mutation-plan:
	@echo "== changed-cell selection for the two pilots (V2-11) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/mutation_plan.py \
	  --repo "$(PILOT_ROOT)" --base "$(DIFF_BASE_RBAC)" --head HEAD \
	  --fixtures spec/pilots/rbac_pg/mutations/mutations.yaml \
	  --cells "$(PILOT_REGISTRY)" \
	  --require-fixtures --json "$(MUTATION_PLAN_RBAC)"
	$(PYTHON) tools/mutation_plan.py \
	  --repo "$(PILOT2_ROOT)" \
	  --base "$(DIFF_BASE_I18N)" --head "$(DIFF_HEAD_I18N)" \
	  --fixtures spec/pilots/craft-i18n/mutations/mutations.yaml \
	  --cells "$(PILOT2_REGISTRY)" \
	  --require-fixtures --json "$(MUTATION_PLAN_I18N)"

mutations:
	@echo "== mutation suites: $(MUTATION_DSN) =="
	$(PYTHON) spec/pilots/rbac_pg/mutations/run_mutations.py \
	  --dsn "$(MUTATION_DSN)" \
	  --ensure-roles \
	  --sharedir "$(MUTATION_SHAREDIR)"

lint-pilot2:
	@echo "== CL1-CL5: second pilot registry (craft-i18n) =="
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	@test -f "$(PILOT2_LEDGER)" || { echo "error: pilot ledger not found: $(PILOT2_LEDGER)" >&2; exit 1; }
	@git rev-parse --verify --quiet "$(BASE_REF)^{commit}" >/dev/null || { echo "error: base ref not found: $(BASE_REF)" >&2; exit 1; }
	@tmp=$$(mktemp --suffix=.yaml); trap 'rm -f "$$tmp"' EXIT; \
	if git show "$(BASE_REF):$(PILOT2_REGISTRY)" > "$$tmp" 2>/dev/null; then \
	  base="--base $$tmp"; \
	else \
	  echo "note: no $(PILOT2_REGISTRY) at $(BASE_REF); first release, CL6 base check skipped"; \
	  base=""; \
	fi; \
	$(PYTHON) tools/cell_lint.py \
	  --root "$(PILOT2_ROOT)" \
	  --ledger "$(abspath $(PILOT2_LEDGER))" \
	  --suite-glob "$(PILOT2_SUITE_GLOB)" \
	  $$base \
	  "$(PILOT2_REGISTRY)"

claims-pilot2:
	@echo "== L1-L6: second pilot claim ledger (craft-i18n) =="
	$(PYTHON) tools/claim_lint.py \
	  --root "$(PILOT2_ROOT)" \
	  --suite-glob "$(PILOT2_SUITE_GLOB)" \
	  --run-log-root "$(CURDIR)" \
	  --tool-output-root "$(CURDIR)" \
	  $(CLAIM_LINT_ARGS) \
	  "$(PILOT2_LEDGER)"

status-pilot2:
	@echo "== status diff: second pilot ledger against $(BASE_REF) =="
	@set -e; \
	git rev-parse --verify --quiet "$(BASE_REF)^{commit}" >/dev/null || { echo "error: base ref not found: $(BASE_REF)" >&2; exit 1; }; \
	tmp=$$(mktemp --suffix=.yaml); trap 'rm -f "$$tmp"' EXIT; \
	if git show "$(BASE_REF):$(PILOT2_LEDGER)" > "$$tmp" 2>/dev/null; then \
	  $(PYTHON) tools/status_diff.py "$$tmp" "$(PILOT2_LEDGER)"; \
	else \
	  echo "note: $(PILOT2_LEDGER) is not in $(BASE_REF); first release, gate skipped"; \
	  printf 'claims: []\n' > "$$tmp"; \
	  $(PYTHON) tools/status_diff.py --first-release "$$tmp" "$(PILOT2_LEDGER)"; \
	fi

unroutable:
	@echo "== U: unroutable share of the pilot taxonomies (V2-25) =="
	$(PYTHON) tools/unroutable.py --max-share 0 \
	  "$(PILOT_REGISTRY)" "$(PILOT2_REGISTRY)"

coverage:
	@echo "== CV1-CV4: coverage report (V2-20) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/coverage_report.py \
	  --cells "$(PILOT_REGISTRY)" \
	  --root "$(PILOT_ROOT)" \
	  --suite-glob "$(PILOT_SUITE_GLOB)" \
	  --ledger "$(PILOT_ROOT)/$(PILOT_LEDGER)"
	$(PYTHON) tools/coverage_report.py \
	  --cells "$(PILOT2_REGISTRY)" \
	  --root "$(PILOT2_ROOT)" \
	  --suite-glob "$(PILOT2_SUITE_GLOB)" \
	  --ledger "$(PILOT2_LEDGER)"

coverage-record:
	@echo "== CV1-CV4: record the coverage measurement (V2-20) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/coverage_report.py \
	  --cells "$(PILOT_REGISTRY)" --root "$(PILOT_ROOT)" \
	  --suite-glob "$(PILOT_SUITE_GLOB)" \
	  --ledger "$(PILOT_ROOT)/$(PILOT_LEDGER)" \
	  --json "$(COVERAGE_RECORD_RBAC)"
	$(PYTHON) tools/coverage_report.py \
	  --cells "$(PILOT2_REGISTRY)" --root "$(PILOT2_ROOT)" \
	  --suite-glob "$(PILOT2_SUITE_GLOB)" \
	  --ledger "$(PILOT2_LEDGER)" \
	  --json "$(COVERAGE_RECORD_I18N)"

diff-coverage:
	@echo "== DC1-DC5: diff coverage of declared choke points (V2-07) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/diff_coverage.py \
	  --repo "$(PILOT_ROOT)" --base "$(DIFF_BASE_RBAC)" --head HEAD \
	  --cells "$(PILOT_REGISTRY)" \
	  --ledger "$(PILOT_ROOT)/$(PILOT_LEDGER)" \
	  --max-unmapped 0
	$(PYTHON) tools/diff_coverage.py \
	  --repo "$(PILOT2_ROOT)" --base "$(DIFF_BASE_I18N)" --head "$(DIFF_HEAD_I18N)" \
	  --cells "$(PILOT2_REGISTRY)" \
	  --ledger "$(PILOT2_LEDGER)" \
	  --max-unmapped 0

diff-coverage-record:
	@echo "== DC1-DC5: record the diff-coverage measurement (V2-07) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/diff_coverage.py \
	  --repo "$(PILOT_ROOT)" --base "$(DIFF_BASE_RBAC)" --head HEAD \
	  --cells "$(PILOT_REGISTRY)" \
	  --ledger "$(PILOT_ROOT)/$(PILOT_LEDGER)" \
	  --max-unmapped 0 --json "$(DIFF_RECORD_RBAC)"
	$(PYTHON) tools/diff_coverage.py \
	  --repo "$(PILOT2_ROOT)" --base "$(DIFF_BASE_I18N)" --head "$(DIFF_HEAD_I18N)" \
	  --cells "$(PILOT2_REGISTRY)" \
	  --ledger "$(PILOT2_LEDGER)" \
	  --max-unmapped 0 --json "$(DIFF_RECORD_I18N)"

choke-points:
	@echo "== CP1-CP2: structural choke-point candidates (V2-22) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/choke_points.py \
	  --root "$(PILOT_ROOT)" \
	  --rules "$(CHOKE_RULES)" --schema "$(CHOKE_SCHEMA)"
	$(PYTHON) tools/choke_points.py \
	  --root "$(PILOT2_ROOT)" \
	  --rules "$(CHOKE_RULES)" --schema "$(CHOKE_SCHEMA)"

choke-points-record:
	@echo "== CP1-CP2: record the choke-point measurement (V2-22) =="
	@test -d "$(PILOT_ROOT)" || { echo "error: pilot root not found: $(PILOT_ROOT)" >&2; exit 1; }
	@test -d "$(PILOT2_ROOT)" || { echo "error: pilot root not found: $(PILOT2_ROOT)" >&2; exit 1; }
	$(PYTHON) tools/choke_points.py \
	  --root "$(PILOT_ROOT)" \
	  --rules "$(CHOKE_RULES)" --schema "$(CHOKE_SCHEMA)" \
	  --json "$(CHOKE_RECORD_RBAC)"
	$(PYTHON) tools/choke_points.py \
	  --root "$(PILOT2_ROOT)" \
	  --rules "$(CHOKE_RULES)" --schema "$(CHOKE_SCHEMA)" \
	  --json "$(CHOKE_RECORD_I18N)"

check-fuzz-triage:
	@echo "== T1-T4: fuzz finding triage (V2-18) =="
	$(PYTHON) tools/fuzz_triage.py \
	  --record "$(FUZZ_RECORD)" \
	  --triage "$(FUZZ_TRIAGE)" \
	  --root .

fuzz-claim-lint:
	@echo "== fuzz: replay $(FUZZ_RECORD) (seed $(FUZZ_SEED), $(FUZZ_RUNS) runs) =="
	@tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	$(PYTHON) tools/fuzz_run.py \
	  --target 'python3 tools/claim_lint.py --root . --docs-glob no-such-docs/*.md --suite-glob no-such-suite/*.py --no-vale @INPUT@' \
	  --corpus "$(FUZZ_CORPUS)" \
	  --record "$$tmp/record.json" \
	  --findings-dir "$$tmp/findings" \
	  --seed "$(FUZZ_SEED)" --runs "$(FUZZ_RUNS)" \
	  --oracle 'stderr-contains:Traceback (most recent call last)' \
	  --oracle 'exit-not-in:0,1,2' || exit 1; \
	$(PYTHON) -c 'import json, sys; a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2])); print("recorded digest:", a["executions_digest"][:16], "| replay digest:", b["executions_digest"][:16]); sys.exit(0 if a["executions_digest"] == b["executions_digest"] else "digest mismatch: the replay is not the recorded run")' \
	  "$(FUZZ_RECORD)" "$$tmp/record.json"; \
	if [ -n "$(FUZZ_OUT)" ]; then \
	  mkdir -p "$(FUZZ_OUT)"; \
	  cp "$$tmp/record.json" "$(FUZZ_OUT)/record.json"; \
	  if [ -d "$$tmp/findings" ]; then cp -r "$$tmp/findings" "$(FUZZ_OUT)/findings"; fi; \
	  echo "fuzz record written to $(FUZZ_OUT)"; \
	fi

mutations-i18n:
	@echo "== mutation fixtures: craft-i18n (cargo, no stand) =="
	$(PYTHON) spec/pilots/craft-i18n/mutations/run_mutations.py \
	  --target "$(PILOT2_ROOT)" \
	  --target-dir "$(PILOT2_MUTATION_TARGET_DIR)"

crosscheck-c02:
	@echo "== C-02: independent row model vs read_catalog, bounded space =="
	CARGO_TARGET_DIR="$(C02_TARGET_DIR)" $(CARGO) run --offline --release --manifest-path "$(C02_MANIFEST)"

crosscheck-c02-mutants:
	@echo "== C-02: model mutation control =="
	CARGO_TARGET_DIR="$(C02_TARGET_DIR)" $(CARGO) run --offline --release --manifest-path "$(C02_MANIFEST)" -- --mutants

proof-plan:
	@echo "== proof plan: $(PROOF_BASE)...$(PROOF_HEAD) against $(PROOF_MANIFEST) =="
	@base=$$(git merge-base "$(PROOF_BASE)" "$(PROOF_HEAD)") || \
	  { echo "error: no merge base for $(PROOF_BASE) and $(PROOF_HEAD)" >&2; exit 2; }; \
	$(PYTHON) tools/proof_plan.py --repo . --base "$$base" \
	  --head "$(PROOF_HEAD)" --manifest "$(PROOF_MANIFEST)"

# The planner's eval suite is only evidence if a broken planner turns it red.
# Runs seven mutants against the full suite (~70s), so it is not in `verify`.
proof-plan-selftest:
	@echo "== proof plan: mutate the planner, require the suite to fail (V2-29) =="
	$(PYTHON) evals/proof-plan/mutation_selftest.py

red-team:
	@echo "== red team: attacks on the real pilot artifacts =="
	$(PYTHON) spec/red-team/run_drills.py

red-team-record:
	$(PYTHON) spec/red-team/run_drills.py --record "$(RED_TEAM_RECORD)"

mutations-all: mutations mutations-i18n

help:
	@echo "targets:"
	@echo "  verify        all static gates (evals, seed registry, both pilot registries, claims, status diffs)"
	@echo "  verify-all    verify plus both mutation batches (needs PostgreSQL and cargo)"
	@echo "  evals         adversarial cases for cell_lint, claim_lint, status_diff, fuzz_run, fuzz_triage, coverage_report, diff_coverage, choke_points"
	@echo "  lint-seed     CL1-CL6 over spec/conveyor/cells.seed.yaml"
	@echo "  lint-pilot    CL1-CL6 over the rbac_pg registry with its claim ledger"
	@echo "  lint-pilot2   CL1-CL5 over the craft-i18n registry with its claim ledger"
	@echo "  claims-pilot  L1-L6 over the rbac_pg claim ledger"
	@echo "  claims-pilot2 L1-L6 over the craft-i18n claim ledger"
	@echo "  status-pilot  status-escalation diff for the rbac_pg ledger"
	@echo "  status-pilot2 status-escalation diff for the craft-i18n ledger"
	@echo "  unroutable    measure U over both pilot taxonomies; fails on any 'other' cell"
	@echo "  coverage      CV1-CV4 over both pilots: cited symbols, unmapped symbols, stale claims, fixtures"
	@echo "  coverage-record  write the two JSON coverage snapshots into spec/coverage/"
	@echo "  diff-coverage  DC1-DC5 over both pilots: changed choke points must map to a claim"
	@echo "  diff-coverage-record  write the two JSON diff-coverage snapshots into spec/diff-coverage/"
	@echo "  choke-points  CP1-CP2 over both pilots: structural choke-point candidates and their cell classes"
	@echo "  choke-points-record  write the two JSON choke-point snapshots into spec/choke-points/"
	@echo "  check-fuzz-triage  T1-T4 over the recorded run and its triage file"
	@echo "  fuzz-claim-lint  replay the recorded fuzz run and compare executions_digest"
	@echo "  mutations     rbac_pg mutation suites (MUTATION_DSN, MUTATION_SHAREDIR)"
	@echo "  invariants    INV1-INV5 over the general-code invariant catalogue (V2-21)"
	@echo "  invariants-record  write the coverage snapshot into spec/invariants/"
	@echo "  sarif         SARIF adapters over SARIF_INPUTS (default: authored fixtures); SARIF_STRICT=--reject-fixtures"
	@echo "  sarif-record  write the normalized report into spec/sarif/"
	@echo "  mutation-plan select fixtures for the cells the pilot diffs touched (V2-11)"
	@echo "  mutations-i18n  craft-i18n mutation fixtures (cargo, no database)"
	@echo "  mutations-all   both mutation batches"
	@echo "  proof-plan    which proofs a diff must re-run (V2-29); optional gate flags live in the tool"
	@echo "  proof-plan-selftest  mutate the planner and require the eval suite to fail"
	@echo "  crosscheck-c02  independent row model vs read_catalog over the declared bounded space"
	@echo "  crosscheck-c02-mutants  every named model edit must be detected"
	@echo "  red-team      attack the real pilot ledger/log/registry; 13 blocked, 1 recorded gap"
	@echo "  red-team-record  rewrite spec/red-team/2026-11-07-drills.json"
