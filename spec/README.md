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
```

## Status

Phase 0: documents, schema, seed registry, `cell_lint` (CL1–CL6, 26
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

Product trials are not open: the `unroutable` share and the numeric thresholds
N and U are recorded as `to-measure` in `conveyor/product-trials.md` (the N
input is measured; U is structurally zero under the current schema, see §2.1),
and no product run counts as improvement statistics until that boundary is
filled.

## Reading order

1. `CONCEPT.md` — thesis, trust policy, layers, taxonomy, verdicts, ceiling.
2. `cell-registry.schema.json` — the machine-readable shape of a cell.
3. `cells.seed.yaml` — uncalibrated seed cells, all `open`.
4. `guard-grammar.md` — what L2 can and cannot model.
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
