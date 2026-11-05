# Iteration 4 — cell registry linter evals (`cell_lint.py`)

Date: 2026-11-05. Scope: `tools/cell_lint.py` (checks CL1–CL6) against a
synthetic adversarial suite. Status: **18/18 cases pass** (run shown below).

## Method

Each case in [`evals/cell-lint/cases/`](../cell-lint/cases/) is a synthetic
registry (plus an optional base registry and claim ledger) with expectations:
for each check CL1–CL6 either a severity that must appear
(`error` / `warning` / `info`) or `none`, plus the expected exit code.
`evals/cell-lint/run_evals.py` materializes each fixture in a temp directory,
runs `cell_lint`, and compares parsed `[CLx] severity` lines against the
expectations.

Fixtures are synthetic and marked as such in every file. A passing run means
the linter's contract holds on the adversarial cases; it is **not** evidence
that any production registry is clean.

## Checks

| Check | Contract |
| --- | --- |
| CL1 structure | required fields, `CELL-<n>` / `D-…` / `C-<n>` IDs, unique IDs, status/kind/failure-mode enums, a test detector needs an artifact or a command |
| CL2 coverage | a non-open cell needs a detector; a cell may not exceed its strongest detector; a detector may not exceed its kind; a non-open detector needs a mutation fixture |
| CL3 evidence | artifacts exist; dates are valid, not in the future, and within the freshness window; a non-open detector has `last_verified` |
| CL4 traceability | `claim_ids` resolve when a ledger is given; a non-open cell has an owner and residual risk; a cell may not claim more than its linked claim |
| CL5 taxonomy | the cell class is declared; titles and failure classes are unique; duplicate entry points and unused classes are visible |
| CL6 escalation | with `--base`, a status may not rise without new detector evidence; downgrades and removals are visible |

## Cases

| Case | Adversarial move | Expected |
| --- | --- | --- |
| `valid-clean` | control: one open cell with limitations and residual risk | no findings |
| `open-without-limitations` | `status=open` drops its limits | CL1 error |
| `non-open-without-detector` | cell claims `tested`, lists no detector | CL2 error |
| `detector-above-cell` | cell claims `tested`, strongest detector is `reviewed` | CL2 error |
| `kind-above-status` | a `test` detector claims `proven` | CL2 error |
| `fake-artifact` | detector artifact does not exist | CL3 error |
| `stale-detector` | detector evidence older than the window | CL3 warning |
| `future-date` | `last_seen` in the future | CL3 warning |
| `duplicate-cell-ids` | two cells share one ID | CL1 error |
| `bad-id-format` | `CELL-1` breaks the stable-ID pattern | CL1 error |
| `unknown-status` | `coverage_status: verified` | CL1 error |
| `taxonomy-class-mismatch` | cell class absent from `taxonomy.classes` | CL5 error |
| `unknown-claim` | `claim_ids: [C-99]` with no such claim | CL4 error |
| `non-open-unassigned` | non-open cell with no owner | CL4 warning |
| `cell-above-claim` | cell claims `reviewed`, linked claim is `open` | CL4 warning |
| `escalation-without-evidence` | `open -> reviewed`, same detector | CL6 error |
| `escalation-with-new-detector` | `open -> reviewed` plus a second detector | CL6 none |
| `downgrade` | `reviewed -> open` | CL6 info |

## Negative control

The runner itself must not pass vacuously. Replacing `cell_lint` with a no-op
script makes every case that expects a finding fail:

```text
$ python3 evals/cell-lint/run_evals.py --cell-lint /tmp/noop_cell_lint.py
...
evals: 2/18 passed
```

The two "passes" are the cases that expect no finding (`valid-clean` and
`escalation-with-new-detector`); every case that expects a finding fails. The
control proves the runner reads findings and exit codes, not just that the
process starts.

## Reproduction

```text
$ python3 evals/cell-lint/run_evals.py
PASS bad-id-format
...
PASS valid-clean
evals: 18/18 passed
```

## Limitations

- The suite is synthetic. It proves the linter's contract on adversarial cases,
  not that any real registry is complete or that the taxonomy is calibrated.
- CL6 evidence identity is a design decision: it compares
  `(kind, artifact, command, mutation_fixture)` and detector IDs. A status edit
  or a newer `last_verified` alone is not new evidence. This matches the
  `status_diff.py` rule but has no independent calibration.
- Structural checks are hand-coded rather than delegated to a JSON Schema
  validator, so they can drift from `cell-registry.schema.json`. The schema
  remains the normative shape; `cell_lint` is the executable subset.
- `owner: unassigned` is allowed and rendered as a warning for non-open cells.
  Making it an error would block a registry that is honest about missing
  ownership.
- The claim cross-check (CL4) and the escalation gate (CL6) run only when
  `--ledger` or `--base` is supplied. A run without them cannot detect drift.
- Coverage is a claim about a cell, not about the code. CL2 checks internal
  consistency; it does not verify that a detector actually exercises the cell.
