# Single local entry point for every static gate (V2-08).
#
#   make verify        every gate that needs no external service
#   make verify-all    verify + the mutation suites on a live stand
#   make mutations     only the mutation suites (needs a built extension)
#
# Nothing here proves a property. A green run means the registries, ledgers,
# and evals are internally consistent; it is not a certificate.

PYTHON ?= python3

# Pilot registry lives in this repository; its artifacts live in the pilot.
PILOT_ROOT ?= ../rbac_pg
PILOT_REGISTRY ?= spec/pilots/rbac_pg/cells.yaml
PILOT_LEDGER ?= docs/claims.yaml
PILOT_SUITE_GLOB ?= setup/*.py
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

.PHONY: verify verify-all verify-repo verify-pilot evals lint-seed lint-pilot \
        claims-pilot status-pilot mutations help

verify: verify-repo verify-pilot

verify-all: verify mutations

verify-repo: evals lint-seed

verify-pilot: lint-pilot claims-pilot status-pilot

evals:
	@echo "== evals: adversarial cases for the linters =="
	$(PYTHON) evals/cell-lint/run_evals.py
	$(PYTHON) evals/linter/run_evals.py
	$(PYTHON) evals/status-diff/run_evals.py

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

help:
	@echo "targets:"
	@echo "  verify        all static gates (evals, seed registry, pilot registry, claims, status diff)"
	@echo "  verify-all    verify plus the mutation suites (needs a live stand)"
	@echo "  evals         adversarial cases for cell_lint, claim_lint, status_diff"
	@echo "  lint-seed     CL1-CL6 over spec/conveyor/cells.seed.yaml"
	@echo "  lint-pilot    CL1-CL6 over the pilot registry with its claim ledger"
	@echo "  claims-pilot  L1-L5 over the pilot claim ledger"
	@echo "  status-pilot  status-escalation diff for the pilot ledger"
	@echo "  mutations     run the mutation suites (MUTATION_DSN, MUTATION_SHAREDIR)"
