# Release Note: NOT NULL Column Migration (PostgreSQL 14–17)

**Status:** Cleared for canary deployment. Full rollout is gated on the open items under Known Gaps.
**Basis of this note:** a staging test run (100 of 100 passing) and statements from the owning team. No production-representative load test, no sanitizer run on the final revision, and no rollback drill are available.

## Summary

This release adds a NOT NULL column with a DEFAULT to an existing table and is intended for deployment without downtime on PostgreSQL 14 through 17. The change is reported as backward-compatible. That property holds for the paths listed under Compatibility and is not a blanket guarantee for every client or every deployment order.

## What Changes

- Schema: one new NOT NULL column with a DEFAULT is added to an existing table.
- Runtime: the service/worker build ships alongside the migration. The stale-worker code path is unchanged from the revision tested last month.

## Compatibility

Supported, based on the default:

- Old clients that INSERT using an explicit column list that omits the new column receive the default and continue to work.
- New clients may read and write the column.
- Existing rows are not rewritten when the default expression is non-volatile; the default is supplied for reads and materialized on write.

Not covered by the "old clients are fine" statement:

- Clients that INSERT without an explicit column list (positional `VALUES`) will fail, because the table's column count changed.
- Clients that use `SELECT *` with positional row decoding, or that validate an exact column set, will observe an extra column.
- Clients that introspect the schema and reject unknown columns.
- Any writer that explicitly supplies NULL; that write now fails with a NOT NULL violation, by design.

Two assumptions are load-bearing and are not evidenced in the material provided. First, that the default expression is non-volatile; a volatile default causes a full table rewrite instead of the fast-default path. Second, that staging exercised the real mixed-version window, with old and new application instances running concurrently against the migrated schema.

## Deployment Behavior

On PostgreSQL 14–17, adding a column with a non-volatile default avoids a table rewrite but still takes a brief ACCESS EXCLUSIVE lock to update the catalog. Under load, that lock request queues behind long-running transactions and can block queries that arrive after it. Operators should:

- set `lock_timeout` and retry the migration rather than waiting indefinitely;
- confirm there are no long-running transactions or open cursors on the table immediately before applying;
- apply the migration before starting new application instances that require the column;
- keep the old and new application versions compatible for the entire drain window, since both will run during a rolling deploy.

Table size may grow gradually after deployment as the default is materialized on new writes. This is expected.

## Evidence Summary

| Claim | Evidence | Status |
|---|---|---|
| Migration applies cleanly | Staging run | Verified in staging only; PostgreSQL version(s) used not stated |
| 100 tests pass | Staging test report | Verified as a count; coverage and per-version breakdown not provided |
| Backward-compatible | Design reasoning plus default | Partially supported; conditional on the paths above |
| Old clients unaffected | Default satisfies omitted-column INSERTs | Supported for that insert path only; read and positional paths unverified |
| Stale-worker path safe | Code unchanged, tested last month | Inherited evidence; not re-verified on this revision |
| No memory-safety regression | ASAN | Not run after the change |
| Rollback works | None | Not exercised |

## Known Gaps

1. **ASAN was not rerun on the final revision.** The stale-worker path is unchanged, so a regression there is unlikely, but "unchanged" is an argument, not a measurement. Code linked into this build outside that path is likewise unmeasured by ASAN.
2. **Rollback was not exercised.** The procedure may be correct; it is untested. Dropping the column also discards every value written since deployment, so rollback is a data-loss decision, not a routine undo.
3. **The 14–17 support range is declared, not demonstrated.** The evidence does not state which PostgreSQL versions staging covered. Confirm the version matrix before publishing version-specific support claims.
4. **No production-scale timing data** for the catalog lock window, and no measurement of the mixed-version window under real client traffic.

## Rollback

Documented but unexercised. For most failure modes, forward-fix is preferable to dropping the column. If destructive rollback is chosen, it requires explicit sign-off and a data-retention decision covering rows written after the migration.

## Risk Statement

Low to moderate. The realistic failure modes are concentrated in the mixed-version deployment window and in clients that decode result sets positionally or insert without column lists. Recommended rollout: canary first, monitor for SQLSTATE 23502 (NOT NULL violation) and schema-mismatch errors, watch `pg_stat_activity` for lock waits during the migration, and close the open items above before declaring the change fully verified.
