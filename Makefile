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

# Use Vale when it is installed, otherwise the built-in L5 scanner.
CLAIM_LINT_ARGS ?= $(shell command -v vale >/dev/null 2>&1 || echo --no-vale)

# Recorded fuzz run (V2-17). The replay target is not part of `verify`: it
# executes the target ~155 times (about a minute) to prove the digest
# reproduces, which is a manual, on-demand check rather than a merge gate.
FUZZ_RECORD ?= spec/fuzz/runs/claim-lint-2026-11-07.json
FUZZ_CORPUS ?= spec/fuzz/corpus/claim-lint
FUZZ_SEED ?= 20261107
FUZZ_RUNS ?= 150

.PHONY: verify verify-all verify-repo verify-pilot verify-pilot2 evals lint-seed \
        lint-pilot lint-pilot2 claims-pilot claims-pilot2 status-pilot \
        status-pilot2 unroutable mutations mutations-i18n mutations-all \
        fuzz-claim-lint help

verify: verify-repo verify-pilot verify-pilot2 unroutable

verify-all: verify mutations-all

verify-repo: evals lint-seed

verify-pilot: lint-pilot claims-pilot status-pilot

verify-pilot2: lint-pilot2 claims-pilot2 status-pilot2

evals:
	@echo "== evals: adversarial cases for the linters =="
	$(PYTHON) evals/cell-lint/run_evals.py
	$(PYTHON) evals/linter/run_evals.py
	$(PYTHON) evals/status-diff/run_evals.py
	$(PYTHON) evals/fuzz/run_evals.py

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
	@echo "== L1-L5: pilot claim ledger =="
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
	@echo "== L1-L5: second pilot claim ledger (craft-i18n) =="
	$(PYTHON) tools/claim_lint.py \
	  --root "$(PILOT2_ROOT)" \
	  --suite-glob "$(PILOT2_SUITE_GLOB)" \
	  --run-log-root "$(CURDIR)" \
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
	  "$(FUZZ_RECORD)" "$$tmp/record.json"

mutations-i18n:
	@echo "== mutation fixtures: craft-i18n (cargo, no stand) =="
	$(PYTHON) spec/pilots/craft-i18n/mutations/run_mutations.py \
	  --target "$(PILOT2_ROOT)" \
	  --target-dir "$(PILOT2_MUTATION_TARGET_DIR)"

mutations-all: mutations mutations-i18n

help:
	@echo "targets:"
	@echo "  verify        all static gates (evals, seed registry, both pilot registries, claims, status diffs)"
	@echo "  verify-all    verify plus both mutation batches (needs PostgreSQL and cargo)"
	@echo "  evals         adversarial cases for cell_lint, claim_lint, status_diff, fuzz_run"
	@echo "  lint-seed     CL1-CL6 over spec/conveyor/cells.seed.yaml"
	@echo "  lint-pilot    CL1-CL6 over the rbac_pg registry with its claim ledger"
	@echo "  lint-pilot2   CL1-CL5 over the craft-i18n registry with its claim ledger"
	@echo "  claims-pilot  L1-L5 over the rbac_pg claim ledger"
	@echo "  claims-pilot2 L1-L5 over the craft-i18n claim ledger"
	@echo "  status-pilot  status-escalation diff for the rbac_pg ledger"
	@echo "  status-pilot2 status-escalation diff for the craft-i18n ledger"
	@echo "  unroutable    measure U over both pilot taxonomies; fails on any 'other' cell"
	@echo "  fuzz-claim-lint  replay the recorded fuzz run and compare executions_digest"
	@echo "  mutations     rbac_pg mutation suites (MUTATION_DSN, MUTATION_SHAREDIR)"
	@echo "  mutations-i18n  craft-i18n mutation fixtures (cargo, no database)"
	@echo "  mutations-all   both mutation batches"
