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
  pilots/
    rbac_pg/
      cells.yaml                  # 29 cells derived from rbac_pg detectors
      README.md                   # calibration, findings, limits
      mutations/
        mutations.yaml            # 5 mutation fixtures, pinned by sha256
        run_mutations.py          # verifies each detector fails as predicted
        README.md                 # what a fixture proves, results, gaps
```

## Status

Phase 0: documents, schema, seed registry, `cell_lint` (CL1–CL6, 18/18
synthetic adversarial cases, see `evals/iteration-4/RESULTS.md`), and one
pilot registry on `rbac_pg` (29 cells, 26 non-open, 3 open, 0 CL1/CL3/CL4
errors, C-18). Five of the pilot's 27 detectors are mutation-verified: each
named suite fails exactly on the predicted tests when its mechanism is
removed. There is no production registry and no claim that the conveyor
exists. Every material statement in `CONCEPT.md` carries a status from the
evidence-first ladder; design intents are `open` and carry limitations.

## Reading order

1. `CONCEPT.md` — thesis, trust policy, layers, taxonomy, verdicts, ceiling.
2. `cell-registry.schema.json` — the machine-readable shape of a cell.
3. `cells.seed.yaml` — uncalibrated seed cells, all `open`.
4. `guard-grammar.md` — what L2 can and cannot model.
5. `../../tools/cell_lint.py` — the executable subset of the cell contract;
   its cases are in `../../evals/cell-lint/`.
6. `pilots/rbac_pg/README.md` — what a real registry looks like and what it
   still cannot prove.

## What this is not

- Not a certification, an audit, or a compliance statement.
- Not a throughput claim. Numbers such as review time or cell count are
  `open` until measured on a pilot.
- Not a replacement for the skills. `CONCEPT.md` depends on
  `negative-test-first`, `evidence-first-docs`, and `invariant-first-code`
  for content and evidence discipline.
