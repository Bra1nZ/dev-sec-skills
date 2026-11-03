# Release note: NOT NULL column with default

**Release:** not supplied. **Target:** PostgreSQL 14–17. **Status:** draft for release review; conditional.

## What changes

One migration adds a NOT NULL column with a DEFAULT to an existing table. The DDL, column, and default expression are not supplied; attach them as E-01. No other schema change is described. An INSERT that omits the column should receive the default; clients predating the column can insert without naming it. Existing rows should read back with the default and satisfy NOT NULL.

## Release position

The team describes the migration as compatible with old clients and low-risk to deploy. This note treats both as compound claims, not results. They depend on the default expression, table size and lock duration, old-client behavior, the staging matrix, ASAN coverage, and rollback. No artifact for any of these is attached.

## Claim summary

Seven claims: 0 proven, 0 model-checked, 0 tested, 0 static-refinement, 0 reviewed, 7 open. `open` means evidence is missing; it is a risk, not a result. The reported staging count closes no claim: suite contents, commit, and PostgreSQL version were not supplied.

## Claim ledger

| ID | Claim | Mechanism | Evidence | Scope / TCB | Status | Limitations | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 | Migration takes the metadata-only path; no long exclusive lock. | PostgreSQL 14–17 fast path for a non-volatile default; NOT NULL from the missing value. | DDL/default not supplied (E-01); lock not measured. | Target tables, PG 14–17. | open | Volatile default forces a rewrite; table size and load unknown. | not supplied |
| C-02 | Existing rows read the default and satisfy NOT NULL. | DEFAULT plus PostgreSQL added-column handling. | No constraint or query artifact; suite contents unknown. | All existing rows. | open | Default volatility unconfirmed; explicit NULL untested. | not supplied |
| C-03 | Old clients read and write without modification. | Default fills omitted INSERT column; explicit reads unchanged. | No old-client test identified. | Old clients in production; PG 14–17. | open | `SELECT *`, cached plans, strict decoders, and explicit NULL untested; client versions unknown. | not supplied |
| C-04 | Staging suite is release evidence for the migration. | Executed staging tests. | Reported 100/100; CI, commit, PG version, test list missing (E-02). | Staging only. | open | Count is not coverage; no old-client, rollback, or ASAN case identified. | not supplied |
| C-05 | Stale-worker path has no memory-safety regression on this commit. | ASAN on the worker path. | Last run reported "last month"; not rerun; report/commit missing (E-03). | Stale-worker path, not the SQL migration. | open | Stale; "unchanged" lacks a diff. Attach a diff/build hash or rerun. | last month (reported) |
| C-06 | Rollback restores the prior schema within the window without data loss. | Documented rollback procedure, not supplied. | Not exercised (E-04). | Production-like data and traffic. | open | Time, locks, and post-deploy values unmeasured; data loss possible. | not exercised |
| C-07 | Behavior holds on PostgreSQL 14–17. | Version-compatible DDL and default handling. | No per-version run; staging version not stated (E-05). | All four majors. | open | One staging run, version unknown, cannot cover four majors. | not supplied |

## Open claims and residual risk

Release gate: close each item with an artifact or a written risk acceptance before publishing as a clean release.

1. **No-rewrite and lock duration (C-01).** Attach the DDL, state default volatility, and measure lock duration on a production-sized table. A volatile default forces a rewrite; plan the window.
2. **Old-client compatibility (C-03).** Name the oldest supported client; test connect, INSERT omitting the column, SELECT of known columns, SELECT *, and prepared-statement reuse.
3. **Rollback (C-06).** Exercise it on a staging copy with production-like data after writes populate the new column. Record elapsed time, locks, and whether post-deploy values survive. If not, require a forward-fix decision.
4. **ASAN (C-05).** Rerun on the release commit, or attach a diff/build hash proving the worker path is identical to the last tested commit. Last month's result is stale.
5. **Version matrix (C-07).** State the staging PostgreSQL version, then test 14–17 or narrow the support statement.
6. **Staging evidence (C-04).** Attach the CI run: commit, PG version, test list, 100/100. A count is not coverage.

No negative test covers old-client compatibility, rollback, or the ASAN path; those claims stay `open`.

## Evidence index

| Ref | Artifact | Command / procedure | Commit | Environment | Date | Result |
| --- | --- | --- | --- | --- | --- | --- |
| E-01 | Migration DDL (not supplied) | Review DDL: column, default volatility, constraints, locks | not supplied | PostgreSQL 14–17 | not supplied | not supplied |
| E-02 | Staging run (not supplied) | Run full suite; export report | not supplied | Staging; version not supplied | not supplied | Reported 100/100; artifact missing |
| E-03 | ASAN report (not supplied) | Run ASAN stale-worker tests, or attach unchanged-path diff | not supplied | Not supplied | Reported last month | Not run for this release |
| E-04 | Rollback record (not supplied) | Migrate, write, roll back, validate schema/data and timing | not supplied | Production-like staging | not supplied | Not exercised |
| E-05 | Version matrix (not supplied) | Run migration and compatibility checks on 14, 15, 16, and 17 | not supplied | Four majors | not supplied | Not supplied |

## Scope and assumptions

- **In scope:** additive schema migration; stale-worker path; PostgreSQL 14–17 support range.
- **Out of scope:** superuser/DBA recovery, backup/restore, replication lag, unnamed client or worker versions.
- **Assumption:** the default expression is non-volatile. If not, C-01 and the deployment window change.
- No claim has an attached artifact.
