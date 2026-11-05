# Mutation fixtures — rbac_pg pilot

These fixtures answer one question the cell registry cannot answer on its own:

> **Can the detector fail at all?**

A green suite is not evidence that a detector is sensitive to the property it
claims. Each fixture below mutates exactly one enforcement artifact in a
throw-away copy of `rbac_pg`, runs the detector suite that is supposed to catch
the regression, and requires the suite to fail **exactly** on the predicted
tests. The target repository is never modified.

This is the first batch: it covers 5 of the pilot's 27 detectors. The remaining
22 have no mutation fixture and keep the `CL2` warning ("not verified").

## What a passing fixture proves

- The detector executes and produces a pass/fail verdict in this environment.
- The named assertion is **coupled** to the mutated mechanism: break the
  mechanism and the assertion flips.
- The rest of the suite still passes, so the mutation is not a blunt
  instrument that breaks everything.

## What it does not prove

- It does not prove the detector is complete. It fails for **this** mutation;
  other bypasses of the same property may still pass.
- It does not prove the property holds in production. A mutation fixture is a
  sensitivity check, not a proof of correctness.
- It does not cover performance, concurrency, or migration paths unless a
  fixture explicitly targets them.

## Results (2026-11-06)

| Fixture | Cell | Detector | Mutation | Expected failures | Observed |
|---|---|---|---|---|---|
| MUT-001 | CELL-018 | D-V191-F1 | `refresh_session()` reads identity and deadline from GUCs instead of the signed blob | F1a, F1b, F1c | 19 OK, 3 FAIL |
| MUT-002 | CELL-019 | D-V191-F3 | `DISABLE ROW LEVEL SECURITY` removed from the dangerous-subcommand list | F3a, F3b | 20 OK, 2 FAIL |
| MUT-003 | CELL-020 | D-V191-F4 | `DISABLE TRIGGER` / `DISABLE ALL` removed from the dangerous-subcommand list | F4a, F4b | 20 OK, 2 FAIL |
| MUT-004 | CELL-015 | D-V16-GUARDS | `guard_truncate()` returns instead of raising | 3 TRUNCATE refusals | 42 OK, 3 FAIL |
| MUT-005 | CELL-012 | D-V17-E1 | `security_events_append_only()` becomes a no-op | UPDATE, DELETE, TRUNCATE refusals | 51 OK, 3 FAIL |

Unmutated baselines on the same stand: `test_v191_fixes.py` 22 OK, `test_v16_guards.py`
45 OK, `test_v17_events.py` 54 OK. `test_fstek.py` was also re-run: 57 OK. The
other six pilot suites reproduced as well: 20, 25, 17, 20, 9 OK and
`test_side_channels.py` 5 OK / 2 GAP.

## Findings

1. **First mutation coverage in the pilot.** Before this batch, 0 of 27
   detectors could be shown to fail. Now 5 can. CELL-012, CELL-015, CELL-018,
   CELL-019 and CELL-020 have a verified detector.

2. **CELL-002 is not mutation-testable at the repository layer.** The F8
   refusal comes from the platform's membership semantics, not from extension
   code: on the Astra stand `F8b` reports "platform blocks" and the extension's
   `ddl_guard` GRANT/REVOKE branch never fires (PostgreSQL does not raise the
   role-membership event trigger for global role objects). On true vanilla
   PostgreSQL 15 the platform allows the grant, so the same detector would fail
   without any code change. The cell stays `tested` with an explicit
   platform-dependence limitation; it has no mutation fixture.

3. **F3 and F4 share one fail-closed branch.** Deleting the
   `IF NOT v_matched_alter OR v_unresolved_alter` branch in `ddl_guard()` makes
   F3a, F3b, F4a and F4b fail together, because unqualified targets do not
   resolve under the guard's `search_path` and therefore rely on that branch.
   The fixtures instead mutate the dangerous-subcommand list, which isolates
   CELL-019 from CELL-020. This is a detector-structure finding: two cells are
   not independently falsifiable through the branch they share.

4. **`test_v191_fixes.py` is not runnable on a truly fresh cluster.** Its
   `make_roles()` runs before the SQL is installed and creates roles
   `IN ROLE rbac_admin`, so `rbac_admin` and `rbac_label_admin` must already
   exist. On a cluster where the extension was never installed the suite stops
   at `role "rbac_admin" does not exist`. This is a reproducibility gap in the
   suite, not in the extension. The runner's `--ensure-roles` performs the
   prerequisite idempotently.

5. **`test_fstek.py` deploys via `CREATE EXTENSION`.** It therefore uses the
   extension files under `pg_config --sharedir`, not the working tree. On the
   recorded stand those files were byte-identical to `sql/rbac--1.9.1.sql`
   (`sha256 d5452f…`), so the 57 OK baseline applies to this commit. A fixture
   for an FSTEC cell would need `make install`, which requires root; none is
   attempted here.

## Environment

Recorded run:

- PostgreSQL 15.17 (Debian 15.17-astra.se2.3r2) on Astra Linux.
- Fresh `tools/stand.sh` cluster, port 55433, trust auth.
- `rbac_pg` at commit `492f23c`.
- Artifact hashes pinned in `mutations.yaml`; a drifted artifact fails the
  preflight instead of silently mutating nothing.

Bring up a stand and run:

```sh
cd /home/admini/projects/rbac_pg
CITADEL_STAND_DIR=/tmp/opencode/stand-mut \
CITADEL_STAND_PORT=55433 tools/stand.sh up

cd /home/admini/projects/dev-sec-skills
python3 spec/pilots/rbac_pg/mutations/run_mutations.py \
    --target /home/admini/projects/rbac_pg \
    --dsn "postgresql://postgres@127.0.0.1:55433/postgres" \
    --ensure-roles
```

Exit code 0 means every fixture failed exactly where predicted. Exit code 1
means at least one fixture did not match; the runner prints missing and
unexpected failures and writes the full suite output to
`<workdir>/results/<fixture>.log`. Exit code 2 means a tool or preflight
error.

Useful flags: `--only MUT-003` (repeatable), `--skip-baseline` (faster when
the unmutated suites are already known green), `--workdir PATH`.

## Adding a fixture

1. Choose a detector with a recorded baseline and identify one mechanism the
   detector claims to test.
2. Write the smallest mutation that breaks that mechanism. Prefer a mutation
   that leaves neighbouring detectors green.
3. Run it and record the **exact** failing test names. If the failure set
   includes unrelated tests, the mutation is not isolating the property; say so
   in `note` rather than trimming the expected set silently.
4. Pin the artifact's `sha256`.
5. Add the fixture id to the detector's `mutation_fixture` field in
   `../cells.yaml`.

## Remaining gaps

- 22 of 27 detectors still have no mutation fixture.
- No fixture targets the migration paths (`test_fstek.py` M-series,
  `test_v16_guards.py` M1, `test_v17_events.py` M1–M4).
- No fixture for the side-channel cells (CELL-026, CELL-027, CELL-028,
  CELL-029): two are `open`, and the other two are configuration-dependent.
- CELL-021 (idempotency), CELL-022 (label ranges), CELL-023 (performance) and
  CELL-024 (claim ledger) are not covered by this batch.
