# Pilot cell registry — `rbac_pg` ("Цитадель")

Date: 2026-11-06. Target: `/home/admini/projects/rbac_pg`, HEAD `492f23c`
(working tree has untracked model and documentation files; see Limitations).
Registry: [`cells.yaml`](cells.yaml). Linter: `tools/cell_lint.py` (CL1–CL6).
Mutation fixtures: [`mutations/`](mutations/README.md).

This is the first registry built against a real repository. The point is
calibration: how many cells one repository actually uses, how many resolve to
real artifacts, how many are linked to claims, and how many detectors can be
shown to fail. It is not a security audit of `rbac_pg`.

## Method

Cells were derived from detectors that already exist in the repository:

- `setup/test_fstek.py` — FSTEC matrix, F1–F15, recorded 57 OK / 0 FAIL;
- `setup/test_v191_fixes.py` — security-audit fixes, F1–F4 and M1–M2,
  recorded 22 OK / 0 FAIL;
- `setup/test_v16_guards.py` — DDL, TRUNCATE and COPY guards, G1–G9,
  recorded 45 OK / 0 FAIL;
- `setup/test_v17_events.py` — events, replay and integrity, E/J/A/I,
  recorded 54 OK / 0 FAIL;
- `setup/test_side_channels.py` — side channels, recorded 5 OK / 0 FAIL /
  2 GAP;
- `setup/test_v15_idempotency.py` — 20 OK / 0 FAIL;
- `setup/test_v151_ranges.py` — 25 OK / 0 FAIL;
- `setup/test_perf_envelope.py` — 9 OK / 0 FAIL;
- `setup/test_v15_security.py` — 17 OK / 0 FAIL;
- `setup/test_v15_ceiling_trigger.py` — 20 OK / 0 FAIL;
- `docs/claims.yaml` — the claim ledger, C-01…C-07.

Each cell names the suite, the test IDs, the claim (where one exists), and the
residual risk. No cell was invented to fill a taxonomy class.

### Evidence policy

`tested` means a test detector exists and its suite has a recorded passing
baseline. Of the 27 detectors, 5 test detectors now also have a mutation fixture
showing that the detector fails when the mechanism is removed. The other 22
(21 test, 1 review) have none, and CL2 keeps warning that they are not
verified. On 2026-11-06 all ten suites were re-run on a fresh PostgreSQL 15.17
stand: `test_fstek.py` 57 OK, `test_v191_fixes.py` 22 OK,
`test_v16_guards.py` 45 OK, `test_v17_events.py` 54 OK,
`test_v15_idempotency.py` 20 OK, `test_v151_ranges.py` 25 OK,
`test_v15_security.py` 17 OK, `test_v15_ceiling_trigger.py` 20 OK,
`test_perf_envelope.py` 9 OK, `test_side_channels.py` 5 OK / 2 GAP.
`reviewed` means a review artifact, not an executable detector. `open` means
either no detector exists or the recorded run shows the property failing.

## Lint result

```text
$ python3 tools/cell_lint.py \
    --root /home/admini/projects/rbac_pg \
    --ledger /home/admini/projects/rbac_pg/docs/claims.yaml \
    spec/pilots/rbac_pg/cells.yaml

registry: spec/pilots/rbac_pg/cells.yaml | cells: 29
  CL1 structure     OK
  CL2 coverage      0 error(s), 0 warning(s), 3 info
  CL3 evidence      OK
  CL4 traceability  0 error(s), 0 warning(s), 22 info
  CL5 taxonomy      0 error(s), 0 warning(s), 3 info
total: 0 error(s), 0 warning(s), 28 info
```

CL1, CL3 and CL4 errors are zero: every required field is present, every
artifact path resolves on disk, every linked claim exists, and no cell claims
more than its strongest detector or its linked claim. CL2 has no warnings: 24
of the 27 detectors have a mutation fixture and the remaining 3 carry a
documented `mutation_exemption`, reported as info. The other info lines are the
22 cells without a claim link, the 3 exemptions, and 3 duplicate failure
classes. `make verify` runs this same command (`--base HEAD` included), so the
numbers cannot drift from the documented invocation. The registry also
validates against `spec/conveyor/cell-registry.schema.json` with `jsonschema`.

An earlier revision of this page reported 22 CL2 warnings. That run predates
the mutation batch: those warnings no longer exist, and the old output is only
in git history.

### Negative control

The clean run is not vacuous. Two mutations of the same registry each produce
an error and exit code 1 (re-run 2026-11-06 with the ledger):

```text
# missing artifact
[CL3] error CELL-001 detector 'D-FSTEC-F2F3' artifact not found: setup/missing_suite.py
total: 1 error(s), 0 warning(s), 28 info

# cell claims proven, detector is only tested
[CL2] error CELL-001 cell claims proven but its strongest detector is tested
total: 1 error(s), 1 warning(s), 28 info
```

The first control proves CL3 reads the filesystem, not just the YAML. The
second proves CL2 compares the cell status against the detector status and CL4
compares it against the linked claim. Neither mutation was added to the
repository; both were run on temporary copies.

`--ledger` is not optional here: without it, CL4 cannot resolve a single
`claim_id`. The CLI now warns when cells reference claims and no ledger is
passed, because an earlier manual run of this gate silently skipped the check
and still exited 0. `make verify` always passes the ledger.

## Calibration

| Measure | Value |
| --- | --- |
| Cells | 29 |
| Non-open cells | 26 (25 `tested`, 1 `reviewed`) |
| Open cells | 3 |
| Detectors | 27 (26 `test`, 1 `review`) |
| Detectors with a mutation fixture | **5 / 27** (CELL-012, 015, 018, 019, 020) |
| Cells linked to a claim | 7 / 29 |
| Cells with no claim | 22 / 29 |
| Claim ledger entries | 7 (C-01…C-07; C-07 is `open`) |
| Duplicate `failure_class` values | 3 (info only) |

Class and failure-mode distribution:

| Class | Cells |
| --- | --- |
| security | 25 |
| correctness | 2 |
| performance | 1 |
| maintainability | 1 |

| Failure mode | Cells |
| --- | --- |
| deny | 16 |
| abort | 6 |
| detect | 6 |
| rollback | 1 |

Entry-point prefixes: `sql:` 51 occurrences, `admin` 23, `import` 2,
`migration` 2, `docs` 2, `log` 1, `batch` 1.

## Cell map

| Cell | Property | Class | Status | Detector | Claim |
| --- | --- | --- | --- | --- | --- |
| CELL-001 | Policy apply only by `rbac_admin` | security | tested | D-FSTEC-F2F3 | C-01 |
| CELL-002 | Admin role membership cannot be granted under `rbac_admin` | security | tested | D-FSTEC-F8 | C-02 |
| CELL-003 | Journals readable only by auditor/admin | security | tested | D-FSTEC-F5F9 | C-03 |
| CELL-004 | Lockout and admin-only unlock | security | tested | D-FSTEC-F11 | C-04 |
| CELL-005 | Directory anchor invariants | security | tested | D-FSTEC-F12 | C-05 |
| CELL-006 | Integrity digest detects rule substitution | security | tested | D-FSTEC-F15 | C-06 |
| CELL-007 | Service roles are NOLOGIN | security | tested | D-FSTEC-F4 | — |
| CELL-008 | `CREATE FUNCTION/PROCEDURE` denied, incl. `pg_temp` | security | tested | D-FSTEC-F7 | — |
| CELL-009 | Security events record the real login | security | tested | D-FSTEC-F10 | — |
| CELL-010 | RSID warning without rejection | security | tested | D-FSTEC-F13 | — |
| CELL-011 | Ceiling change bumps `auth_epoch` | security | tested | D-FSTEC-F14, D-V15-CEILING | — |
| CELL-012 | Security events are append-only | security | tested | D-V17-E1 | — |
| CELL-013 | Second audit channel survives rollback | security | tested | D-V17-E2 | — |
| CELL-014 | Token replay refused before role checks | security | tested | D-V17-J1 | — |
| CELL-015 | DDL/TRUNCATE/policy guards | security | tested | D-V16-GUARDS | — |
| CELL-016 | Tenant and MAC-ceiling isolation | security | tested | D-V15-SEC | — |
| CELL-017 | Foreign trap table not labelled | security | tested | D-V191-F2 | — |
| CELL-018 | GUC context tampering does not change identity | security | tested | D-V191-F1 | — |
| CELL-019 | DDL guard fail-closed on comments/ONLY/multi-statement | security | tested | D-V191-F3 | — |
| CELL-020 | Trigger disable blocked and tamper-evident | security | tested | D-V191-F4 | — |
| CELL-021 | `apply_policy_document` is idempotent | correctness | tested | D-V15-IDEMPOTENCY | — |
| CELL-022 | Label ranges and migration clamp | correctness | tested | D-V151-RANGES | — |
| CELL-023 | Performance envelope of enforcement | performance | tested | D-PERF-ENVELOPE | — |
| CELL-024 | Claims name mechanism, artifact, commit, tests | maintainability | reviewed | D-CLAIM-LEDGER | — |
| CELL-025 | PostgreSQL 14 install rejected | security | open | — | C-07 |
| CELL-026 | `UNIQUE(id)` existence oracle | security | open | — | — |
| CELL-027 | FK probe does not reveal an invisible parent | security | tested | D-SIDE-FK | — |
| CELL-028 | `secure_table` rejects FK to a protected table | security | open | — | — |
| CELL-029 | `pg_stats` does not leak protected values | security | tested | D-SIDE-PGSTATS | — |

## Findings

### 1. The verify-the-verifier gap is now covered for every detector, with three named exceptions

The mutation batch (`mutations/README.md`) covers all 27 detectors: 24 have a
fixture that mutates one artifact in a copy of the repository and requires the
named suite to fail exactly on the predicted tests; 3 carry a documented
`mutation_exemption`. All 25 fixtures matched on the 2026-11-06 stand. Unmutated
controls stayed green, so the mutations, not the environment, caused the
failures. Do not raise a cell above `tested` on the strength of a baseline
alone.

The three exemptions are not free passes:

- **CELL-002** — F8 passes because the Astra/PP1C platform refuses the grant
  before the extension guard runs. On vanilla PostgreSQL 15 the platform allows
  it, so the same detector should fail with no code change. No repository
  mutation can flip it.
- **CELL-027** — the FK-trigger channel is a property of the engine and the
  suite builds the schema itself.
- **CELL-029** — `pg_stats` privileges are a configuration control, asserted on
  the live stand.

Two findings limit how far the fixtures generalise:

- **F3 and F4 share one fail-closed branch.** Removing the branch makes F3a,
  F3b, F4a and F4b fail together. The fixtures therefore mutate the
  dangerous-subcommand list to separate CELL-019 from CELL-020. The two cells
  are not independently falsifiable through the branch they share.
- **A fixture is a sensitivity check, not a completeness proof.** It shows the
  detector fails for *this* mutation; other bypasses of the same property may
  still pass.

Partial exceptions inside some suites are still not per-cell fixtures:
`test_v191_fixes.py` M1 reproduces the 1.9 vulnerability, F2d/F3c/F3d are
positive controls, `test_v16_guards.py` G9 checks the internal channel, and
`test_perf_envelope.py` carries a regression history. The linter cannot
attribute them to a cell.

### 2. The claim ledger is not a coverage map

`docs/claims.yaml` links 7 of 29 cells. It covers the FSTEC matrix
(C-01…C-06) and the open PostgreSQL 14 item (C-07). It does not cover:

- the DDL guard family (CELL-015, CELL-019, CELL-020);
- the audit event family (CELL-009, CELL-012, CELL-013);
- replay (CELL-014);
- idempotency and label ranges (CELL-021, CELL-022);
- performance (CELL-023);
- the 22 cells listed above.

A clean claim ledger therefore does not mean the registry is covered. The two
artifacts measure different things: the ledger records what the project
*claims*, the registry records what has a *detector*. The pilot's 22 unlinked
cells are the concrete size of that gap for this repository.

### 3. Recorded gaps stay visible; only the failing ones are open

`setup/test_side_channels.py` records 5 OK and 2 GAP. The registry turns that
into four cells, but it does not mark all four `open`:

- CELL-026 (П-1) is `open`: a global `UNIQUE(id)` leaks the existence of an
  invisible row through `23505`.
- CELL-027 is `tested`: the FK probe did not disclose an invisible parent on
  the recorded model. TESTING.md still warns that the FK trigger reads the
  parent as the owner, so the cell carries that as residual risk.
- CELL-028 (П-2 contract) is `open`: `secure_table()` accepts a table with a FK
  to a protected table, although the reference contract expects `0P000`.
  TESTING.md records no actual disclosure today; the contract is still not
  met.
- CELL-029 is `tested`: `pg_stats` was empty for the application role on the
  recorded server. This is a configuration control, not a code guard, and must
  be re-run when catalog privileges change.

CELL-026 is PostgreSQL core behaviour: the extension can mitigate it by
requiring the `UNIQUE(tenant_id, id)` convention in `secure_table()`, but it
does not do so today. CELL-028 is the layer defect the extension can close
directly.

CELL-025 is C-07: installation on PostgreSQL 14 is a deployment rule, not a
code check. The claim is `open`, the cell is `open`, and nothing was upgraded
to look better.

### 4. Calibration says 29 cells for one extension, not ~200

The concept's "~200" (C-11) is a design estimate for a platform with several
repositories and layers. One PostgreSQL extension repository with a mature
security test suite produced 29 cells, 24 of them covered. That is consistent
with a few hundred cells for a multi-component product, but it does not confirm
the number. The unroutable share is still unmeasured: no external finding was
routed through the taxonomy in this pilot.

The distribution is also skewed: 25 of 29 cells are security. That is what the
repository's detectors actually cover, not a taxonomy failure. Correctness,
performance and maintainability each have one or two cells; a second pilot on a
different repository is needed before changing the class list.

Three `failure_class` values repeat (`broken-access-control`,
`privilege-escalation`, `existence-oracle`). CL5 reports this as info. The
taxonomy is coarser than the failure classes; splitting them now would be an
uncalibrated change.

### 5. The prose layer is not clean

`tools/claim_lint.py --no-vale --root . --suite-glob 'setup/*.py'
docs/claims.yaml` returns L1–L4 clean, 0 errors, and 14 L5 warnings about
unqualified absolutes in Russian docs. Four of those warnings are in tracked
files (`ROLES.md`, `COMPARISON_ASTRA.md`, `Public.md`); ten are in untracked
local documentation (`MODEL.md`, `FSTEC-GAP.md`, `SCOPE.md`,
`docs/persey/INDEX.md`). The warnings do not block the pilot, but they are the
same class of overclaim the `evidence-first-docs` skill exists to remove.

## Decisions recorded 2026-11-06

- **Claim ledger.** `docs/claims.yaml` stays a FSTEC-matrix artifact
  (C-01…C-07). It is not extended to the 22 unlinked cells: those cells are
  backed by test detectors, not by claims, and widening the ledger would blur
  the difference between "what the project claims" and "what has a detector".
  The registry remains the coverage map; the ledger remains the claim map.
  Revisit when a second consumer needs linked claims.
- **CELL-028.** Stays `open`. The fix belongs in `rbac_pg`: `secure_table()`
  should reject a foreign key to a protected parent with `0P000`. Until that
  ships, the contract gap is an accepted residual. It was not patched here
  because the target repository is read-only for this pilot.
- **CELL-026.** Stays `open`. The oracle is PostgreSQL core behaviour. The
  extension-level mitigation is to require `UNIQUE(tenant_id, id)` in
  `secure_table()`; that is a design change, not a test fix.
- **CELL-029.** Stays `tested` as a configuration control. Re-run C4 whenever
  catalog privileges change; the cell must not be read as a code guard.

## What this proves

- The cell contract is instantiable on a real repository: 29 cells, all
  required fields, all artifact paths resolving, 0 CL1/CL3/CL4 errors.
- The status ladder is usable without inflation: 25 `tested`, 1 `reviewed`,
  3 `open`, and the 3 open cells are exactly the two recorded gaps and the open
  claim.
- The linter is fast enough for a per-commit gate on this repository (well
  under a second on 29 cells).
- The two independent checks agree on traceability: `claim_lint` L1–L4 clean,
  `cell_lint` CL4 with no errors (22 infos are the unlinked cells).
- 24 of 27 detectors are falsifiable: the named suites fail exactly on the
  predicted tests when the mechanism is removed, and stay green otherwise. The
  other 3 carry a documented exemption, so their verdict rests on an argument,
  not on a mutation.
- All ten suites reproduce their recorded baselines on a fresh PostgreSQL 15.17
  stand, including the two recorded side-channel GAPs (П-1, П-2). The
  performance thresholds remain hardware-specific.

## What this does not prove

- That any security property holds in production. All ten suites were re-run on
  one stand; `tested` still rests on tests, not on a proof.
- That the 3 exempted detectors can fail. 24 of 27 detectors have a mutation
  fixture; the other 3 are argued, not measured.
- That the mutation fixtures are complete. Each fixture shows sensitivity to
  one mutation, not the absence of other bypasses.
- That the registry is complete. It covers the detectors that exist; a missing
  detector produces no cell, and this pilot did not hunt for missing cells
  beyond the recorded GAPs.
- That 29 is the right number. One repository, one reviewer, one day.
- That ownership is real. `owner: rbac_pg maintainer` is a role, not a named
  person.

## Reproduction

```bash
# all static gates at once (from dev-sec-skills)
cd /home/admini/projects/dev-sec-skills
make verify

# or one at a time: registry lint
python3 tools/cell_lint.py \
  --root /home/admini/projects/rbac_pg \
  --ledger /home/admini/projects/rbac_pg/docs/claims.yaml \
  spec/pilots/rbac_pg/cells.yaml

# claim ledger lint (in the target repository); drop --no-vale when Vale is
# installed
cd /home/admini/projects/rbac_pg
python3 tools/claim_lint.py --no-vale --root . --suite-glob "setup/*.py" docs/claims.yaml

# the test suites themselves need a stand:
cd /home/admini/projects/rbac_pg
CITADEL_STAND_DIR=/tmp/opencode/stand-mut \
CITADEL_STAND_PORT=55433 tools/stand.sh up
export ADMIN_DATABASE_URL="postgresql://postgres@127.0.0.1:55433/postgres"
python3 setup/test_fstek.py
python3 setup/test_v191_fixes.py
python3 setup/test_v16_guards.py
python3 setup/test_v17_events.py

# mutation fixtures: mutate a copy, run the detector, require the predicted
# failures; the target repository is not modified
cd /home/admini/projects/dev-sec-skills
python3 spec/pilots/rbac_pg/mutations/run_mutations.py \
  --target /home/admini/projects/rbac_pg \
  --dsn "$ADMIN_DATABASE_URL" --ensure-roles \
  --sharedir /tmp/opencode/pgmut/usr/share/postgresql/15/extension
```

`--ensure-roles` is required on a fresh cluster: `test_v191_fixes.py` creates
login roles `IN ROLE rbac_admin` before it installs the SQL, so the extension's
global roles must already exist.

## Next evidence, in priority order

1. Add migration-path mutation fixtures: the `test_fstek.py` M-series,
   `test_v16_guards.py` M1, and `test_v17_events.py` M1–M4. Per-detector
   coverage is complete (24 fixtures + 3 exemptions); the uncovered surface is
   the migration and upgrade path.
2. Close the claim-ledger gap: 22 of 29 cells have no `claim_id`, so CL4 has
   nothing to resolve for them. This is a registry-to-ledger gap, not a lint
   failure (Finding 2).

The claim-ledger and side-channel questions are recorded as decisions above,
not left open. Reopen them only with new evidence.

## Limitations

- The target repository has untracked files (`MODEL.md`, `FSTEC-GAP.md`,
  `SCOPE.md`, `model/`, `docs/persey/`) that were present during the review.
  The registry cites only tracked test artifacts except where a path is
  explicitly a documentation artifact.
- The recorded baselines were produced on two clusters (ЗСУБД and PP1C) on
  2026-10-30. All ten were reproduced on a third, fresh 15.17 stand on
  2026-11-06.
- `cell_lint` checks internal consistency, not truth. A cell can be `tested`
  and wrong if the test asserts the wrong thing.
- The registry is a snapshot. A change to a suite changes the detector's
  identity only if `cell_lint` is re-run with `--base`; `make verify` passes
  `--base HEAD`, so an uncommitted edit that raises a status without new
  detector evidence is rejected. There is still no released base for this
  pilot: the escalation gate over releases starts with the first release that
  contains the claim ledger.
