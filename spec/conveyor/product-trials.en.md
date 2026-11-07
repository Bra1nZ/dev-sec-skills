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
| 1 | All gates run by one command | `make verify` (V2-08) | exit 0 | measured 2026-11-06: exit 0 |
| 2 | The `rbac_pg` pilot is clean | `cell_lint` | 0 error | measured 2026-11-06: 0 error / 0 warning |
| 3 | A second pilot on non-RBAC code | V2-24 | 0 CL1–CL6 errors | measured 2026-11-06: `cell_lint` 0 error / 0 warning / 1 info (14 cells, 13 `tested`, 1 `open`), CL6 OK against the commit that first contains the registry; `claim_lint` 0 error |
| 4 | Mutation coverage of security detectors | `run_mutations.py` + registry (§2.1) | ≥ N = 87.5 % | fixed 2026-11-07: 21/24 = 87.5 %; artifact — `spec/pilots/*/cells.yaml` and `spec/pilots/*/mutations/README.md` at the measurement commit, recorded before the first product run |
| 5 | Every `tested` security detector has either a mutation fixture or a documented `mutation_exemption` | fixture or exemption | 100 % accounted for; exemptions are listed and count as debt | measured 2026-11-06: `rbac_pg` 24 fixtures + 3 exemptions; `craft-i18n` 1 fixture, 0 exemptions |
| 6 | `unroutable` share in the taxonomy | V2-25 | ≤ U = 0.0 % | fixed 2026-11-07: 0/43; the escape hatch (`taxonomy_class`/`failure_mode` = `other` + `routing_note`) exists and is measured by `tools/unroutable.py --max-share 0`; before the hatch, 0 was structural, see §2.1 |
| 7 | `claim_lint`, `status_diff`, evals | `make verify` | 0 error | run 2026-11-07: `claim_lint` 0 error (1 L5 and 6 L2 warnings on `rbac_pg` — the ledger has no run_record; 0 warnings on `craft-i18n`), `cell-lint` 40/40 and 14/14 cases, `linter` 35/35, `fuzz` 5/5 and `fuzz-triage` 13/13 (replay of the recorded run is `make fuzz-claim-lint`, outside `make verify`: about a minute; the triage gate is `make check-fuzz-triage` inside `make verify`), `status-diff` 13 + 1 known GAP: `status_diff` alone cannot see re-dating, and a run_record catches it only when present; without an external anchor (C-13) a consistent forgery passes |

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
  `taxonomy_class` is `other` or whose `failure_mode` is `other` (the V2-25
  escape hatch; both require a non-empty `routing_note`). Denominator: all
  cells of all pilots on the measurement date. This is the taxonomy share
  (V2-25), not the share of guards outside the L2 grammar: the latter is
  counted separately per `guard-grammar.en.md` (C-13) and does not enter U.
  `tools/unroutable.py` computes it; `make verify` runs it with
  `--max-share 0`, so any `other` cell fails the gate until a new artifact and
  a new threshold are recorded.

Both formulas are repeated verbatim in the measurement artifact, so the number
cannot be recalculated under a different formula.

#### Fixed thresholds, 2026-11-07 (V2-32)

Artifacts: the registries `spec/pilots/rbac_pg/cells.yaml` and
`spec/pilots/craft-i18n/cells.yaml`; the recorded mutation runs in
`spec/pilots/*/mutations/README.md`; for U, the output of `make unroutable`
(0/29 and 0/14) at this commit.

| Metric | Formula | Value | Threshold |
|---|---|---|---|
| N | non-open `security` detectors with a `mutation_fixture` / all non-open `security` detectors | 21/24 = 87.5 % | **N = 87.5 %** |
| U | cells with `taxonomy_class=other` or `failure_mode=other` / all cells | 0/43 = 0.0 % | **U = 0.0 %** |

N may not be below 87.5 % without a new artifact. The three exemptions are
debt, not coverage: 20/23 and 1/1 give 21/24, not 24/24.

U = 0 is an observation, not a structural impossibility. Before V2-25 the
schema rejected an undeclared class and an unknown mode, so a cell could not
"fail to route" and reach the count: 0 was a property of the linter. After
V2-25 `other` is reachable, requires `routing_note` and is counted, yet none of
the 43 cells uses it. Any use raises U and fails `make verify` until the
threshold is revisited with a new artifact and an entry in §7.

Measurement bounds: two pilots (29 + 14 cells), one PostgreSQL extension and
one Rust crate; the sample is not representative of every stack. N counts the
existence of a fixture, not its quality; U counts the registry taxonomy only,
not guards outside L2.

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

## 6. Current state (2026-11-07)

- `rbac_pg`: 29 cells; 24 detectors with a mutation fixture and 3 with a
  documented `mutation_exemption`; `cell_lint` 0 error / 0 warning,
  `claim_lint` 0 error and 6 L2 warnings — the ledger lives in the target
  repository, has no run_record, and is not modified by this repository. The
  escalation gate is in first-release mode: the ledger is newer than `v1.3.1`.
- `craft-i18n`: 14 cells; 12 fixtures and 1 exemption; `cell_lint` 0 error,
  `claim_lint` 0 error / 0 warning. All 7 test claims carry a run_record
  (`spec/pilots/craft-i18n/runs/`): log and artifact hashes, exit code and
  executed IDs are checked on every run.
- N = 87.5 % (21/24) and U = 0.0 % (0/43) are fixed in §2.1 with artifacts from
  2026-11-07. `make verify` — exit 0, including evals 40/40 + 35/35 + 5/5 + 13/13 + 13 with one
  known GAP.

Consequence: **the boundary is filled, but product trials are not open yet.**
The thresholds are fixed before the first product run; opening requires §5
(including the §3.2 baseline) and the V2-33 checklist. Any product run before
that remains exploration and does not enter the improvement statistics.

## 7. Document changes

| Date | Change | Artifact | Reason |
|---|---|---|---|
| 2026-11-06 | Draft created: entry criteria and protocol | this file | V2-31 |
| 2026-11-07 | V2-01/V2-02: run_record in the schema and L1/L2 checks; all 7 craft-i18n test claims carry log and artifact hashes | `spec/pilots/craft-i18n/runs/`, `claims.yaml` | run-record |
| 2026-11-07 | V2-25: the `other` + `routing_note` escape hatch; U measured and gated at `--max-share 0` | `tools/unroutable.py`, `cell-registry.schema.json` | V2-25 |
| 2026-11-07 | V2-32: N = 87.5 %, U = 0.0 % fixed with artifacts | §2.1 | V2-32 |
