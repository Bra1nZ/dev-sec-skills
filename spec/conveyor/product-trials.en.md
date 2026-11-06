# Product-trial boundary

Status: draft, 2026-11-06.

This document fixes the moment when dev-sec-skills may be taken to a real
product, and the protocol under which improvements count as clean. Its purpose
is not to start trials as early as possible, but to prevent metrics from being
chosen after the result is known.

The main rule: **a number becomes a threshold only together with a measurement
artifact recorded before the first product run.** A number without an artifact
is an opinion, not a criterion.

## 1. Terms

- **Product run** — applying the solution to a real product or a fragment of it,
  with the inputs, environment, and result recorded.
- **Baseline** — the same metrics measured on the same product before the
  solution is applied.
- **Measurement artifact** — a recorded run: command, environment, product and
  solution versions, `exit_code`, output or its hash, date.
- **Statistics** — a set of product runs whose baseline and metrics were
  registered before the start and whose cases are all recorded, including
  failed ones.

## 2. Entry criteria

All criteria are mandatory. A criterion with an unfilled threshold is not met;
it is not "met by default".

| # | Criterion | Check | Threshold | Threshold status |
|---|---|---|---|---|
| 1 | All gates run by one command | `make verify` (V2-08) | exit 0 | not met: no `Makefile` yet |
| 2 | The `rbac_pg` pilot is clean | `cell_lint` | 0 error | measured 2026-11-06: 0 error / 0 warning |
| 3 | A second pilot on non-RBAC code | V2-24 | 0 CL1–CL6 errors | to-measure: pilot not started |
| 4 | Mutation coverage of security detectors | `run_mutations.py` + registry (§2.1) | ≥ N | to-measure: N fixed after V2-32 |
| 5 | Every `tested` security detector has either a mutation fixture or a documented `mutation_exemption` | fixture or exemption | 100 % accounted for; exemptions are listed and count as debt | measured 2026-11-06 on `rbac_pg`: 24 fixtures + 3 exemptions |
| 6 | `unroutable` share in the taxonomy | V2-25 | ≤ U | to-measure: U fixed after V2-32 |
| 7 | `claim_lint`, `status_diff`, evals | repository commands | 0 error | run 2026-11-06: `claim_lint` 0 error, `cell-lint` 25/25, `linter` 12/12, `status-diff` 8 + 1 known GAP |

Fixing rule: N or U enters the table only with a reference to the measurement
artifact. The artifact must be recorded **before** the first product run. If the
measurement is missing, criterion 3, 4, or 6 is not met.

Criterion 5 does not compensate for criterion 4: a detector with a
`mutation_exemption` counts as accounted for, not as covered, so an
all-exempted set passes criterion 5 and fails criterion 4.

### 2.1 Definitions of N and U

The formulas are fixed together with the thresholds; otherwise the same number
can be counted in different ways.

- **N — mutation coverage of security detectors.** Numerator: detectors of class
  `security` whose `status` is not `open` and that have a `mutation_fixture`.
  Denominator: all detectors of class `security` whose `status` is not `open`.
  Detectors with a `mutation_exemption` do not enter the numerator and are
  listed separately as debt: an exemption means "a mutation cannot break this",
  not "verified by mutation". The target N is set after V2-32 and may not be
  lower than the value already reached on the pilots without a new artifact.
- **U — the `unroutable` share of the taxonomy.** Numerator: cells whose
  failure class routes neither into `taxonomy.classes` nor into a known
  failure mode. Denominator: all cells of all pilots on the measurement date.
  This is the taxonomy share (V2-25), not the share of guards outside the L2
  grammar: the latter is counted separately per `guard-grammar.en.md` (C-13)
  and does not enter U.

Both formulas are repeated verbatim in the measurement artifact, so the number
cannot be recalculated under a different formula.

## 3. Improvement measurement protocol

### 3.1 Metrics

Metrics and their collection method are fixed before the start. The set below is
the mandatory minimum; metrics may be added, and may be removed only with an
entry in §7.

| ID | Metric | Definition | Unit | Collection |
|---|---|---|---|---|
| M1 | Defects found | Defects found by a negative test, mutation, or review; recorded separately before and after the solution | count, with class and severity | case log; every case → cell + detector + fixture |
| M2 | False-positive share | Findings the product judged non-defects divided by all findings | share | case log with the product's decision recorded |
| M3 | Claim-map cost | Time and number of steps to build the invariant map for a chosen fragment | minutes, steps | before/after measurement with the same procedure |
| M4 | Diff coverage | Share of changed choke-point paths and symbols mapped to a claim | share | V2-07, same extractor and threshold |

### 3.2 Baseline

The baseline is recorded before the solution is applied: same product, same
fragment, same version, same stand, same measurement procedure. The minimum
run record is the command, environment, product and solution versions,
`exit_code`, output or its hash, and date. If the baseline is not recorded, the
improvement is not measured.

### 3.3 Statistics hygiene

- **Every** product case is recorded, including failed and withdrawn ones.
- Every case maps to a cell, a detector, and a fixture (or an exemption).
- Metrics and thresholds do not change during a trial. A change is a new entry
  in §7 with a date, reason, and artifact; old runs are not recalculated under
  the new threshold.
- Publish a distribution, not only an average (CONCEPT §13, item 5).
- Environment and noise are recorded; unstable metrics use repeated runs and a
  median, as in `test_perf_envelope.py`.
- Cherry-picking is forbidden: a case may not be removed from the statistics
  after its result is known.

## 4. What does not prove an improvement

- A green suite without a baseline and without a recorded environment.
- A single case chosen after the result is known.
- A lower false-positive rate achieved by deleting detectors without recording
  which properties are left without a detector.
- A fixture count without naming the detectors that remain under an exemption.
- Any "it got better" claim without a distribution and a threshold fixed in
  advance.

## 5. Opening procedure

1. Fill the §2 table; attach an artifact for every "to-measure".
2. Record the baseline per §3.2.
3. Register the metrics and thresholds per §3.1.
4. Only then run product cases.
5. Record every case in the log; after closing, publish a report with the
   distribution and artifact links.

Enforcement starts as this document. A linter for §2 is added after the criteria
stabilise (V2-33); until then the checklist is filled by hand when a product
sprint opens.

## 6. Current state (2026-11-06)

- `rbac_pg`: 24 detectors with a mutation fixture and 3 with a documented
  `mutation_exemption`; `cell_lint` — 0 error / 0 warning.
- The second pilot on non-RBAC code has not started.
- The `unroutable` share has not been measured.
- Thresholds N and U are not fixed.

Consequence: **product trials are not open.** Any product run before §2 is
filled remains exploration and does not enter the improvement statistics.

## 7. Document changes

| Date | Change | Artifact | Reason |
|---|---|---|---|
| 2026-11-06 | Draft created: entry criteria and protocol | this file | V2-31 |
