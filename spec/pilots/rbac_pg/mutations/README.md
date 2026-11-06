# Mutation fixtures — rbac_pg pilot

These fixtures answer one question the cell registry cannot answer on its own:

> **Can the detector fail at all?**

A green suite is not evidence that a detector is sensitive to the property it
claims. Each fixture below mutates exactly one enforcement artifact in a
throw-away copy of `rbac_pg`, runs the detector suite that is supposed to catch
the regression, and requires the suite to fail **exactly** on the predicted
tests. The target repository is never modified.

The batch now covers all 27 detectors that exist in the pilot: 24 have a
mutation fixture, and the other 3 carry a documented `mutation_exemption` for a
platform, configuration, or core-engine property that no repository source
mutation can flip. `cell_lint` reports 0 CL2 warnings.

## What a passing fixture proves

- The detector executes and produces a pass/fail verdict in this environment.
- The named assertion is **coupled** to the mutated mechanism: break the
  mechanism and the assertion flips.
- The rest of the suite still passes, so the mutation is not a blunt
  instrument that breaks everything.
- A command-mode fixture (MUT-025) proves the linter's exit code and finding
  class, not only its prose output.

## What it does not prove

- It does not prove the detector is complete. It fails for **this** mutation;
  other bypasses of the same property may still pass.
- It does not prove the property holds in production. A mutation fixture is a
  sensitivity check, not a proof of correctness.
- It does not cover performance, concurrency, or migration paths unless a
  fixture explicitly targets them.
- An exemption is a documented argument, not a measurement. It says a source
  mutation cannot move the verdict, not that the verdict is independently
  verified.

## Results (2026-11-06)

### FSTEC batch — deployed through `CREATE EXTENSION` (sharedir)

| Fixture | Cell | Detector | Mutation | Failing assertions | Observed |
|---|---|---|---|---|---|
| MUT-006 | CELL-007 | D-FSTEC-F4 | admin role provisioned as `LOGIN` | F4 | 56 OK, 1 FAIL |
| MUT-007 | CELL-001 | D-FSTEC-F2F3 | application role receives the policy-control plane | F3 | 56 OK, 1 FAIL |
| MUT-008 | CELL-003 | D-FSTEC-F5F9 | audit reader runs with definer table rights | F9a, F9b | 55 OK, 2 FAIL |
| MUT-009 | CELL-008 | D-FSTEC-F7 | routine DDL authorization removed | F7a–F7c, F7f | 53 OK, 4 FAIL |
| MUT-010 | CELL-009 | D-FSTEC-F10 | audit default loses the real session login | F10a, F10c | 55 OK, 2 FAIL |
| MUT-011 | CELL-004 | D-FSTEC-F11 | application role receives the unlock plane | F11b | 56 OK, 1 FAIL |
| MUT-012 | CELL-005 | D-FSTEC-F12 | I1 target guard returns before validation | F12a–F12c, F13c, F14a | 52 OK, 5 FAIL |
| MUT-013 | CELL-010 | D-FSTEC-F13 | RSID format warning disabled | F13b | 56 OK, 1 FAIL |
| MUT-014 | CELL-011 | D-FSTEC-F14 | ceiling change no longer bumps `auth_epoch` | F14a | 56 OK, 1 FAIL |
| MUT-015 | CELL-006 | D-FSTEC-F15 | mismatch reported as intact | F15a | 56 OK, 1 FAIL |

Unmutated FSTEC baseline on the same stand: **57 OK, 0 FAIL**.

### Detector batch — direct SQL deployment and command mode

| Fixture | Cell | Detector | Mutation | Failing assertions | Observed |
|---|---|---|---|---|---|
| MUT-001 | CELL-018 | D-V191-F1 | identity and deadline read from GUCs | F1a–F1c | 19 OK, 3 FAIL |
| MUT-002 | CELL-019 | D-V191-F3 | `DISABLE RLS` no longer recognized | F3a, F3b | 20 OK, 2 FAIL |
| MUT-003 | CELL-020 | D-V191-F4 | `DISABLE TRIGGER` no longer recognized | F4a, F4b | 20 OK, 2 FAIL |
| MUT-004 | CELL-015 | D-V16-GUARDS | `guard_truncate()` returns instead of raising | 3 TRUNCATE/GUC refusals | 42 OK, 3 FAIL |
| MUT-005 | CELL-012 | D-V17-E1 | append-only trigger becomes a no-op | UPDATE, DELETE, TRUNCATE refusals | 51 OK, 3 FAIL |
| MUT-016 | CELL-011 | D-V15-CEILING | trigger returns early on every UPDATE | C2–C5 epoch assertions | 15 OK, 5 FAIL |
| MUT-017 | CELL-013 | D-V17-E2 | `RAISE LOG` channel removed | E2 + J1/integrity cascades | 48 OK, 6 FAIL |
| MUT-018 | CELL-014 | D-V17-J1 | replay INSERT becomes an upsert | replay refusal, ordering, LOG | 51 OK, 3 FAIL |
| MUT-019 | CELL-016 | D-V15-SEC | MAC ceiling neutralised in the policy | P0 visibility, tenant/ceiling regression | 15 OK, 2 FAIL |
| MUT-020 | CELL-017 | D-V191-F2 | ownership check disabled | F2b | 21 OK, 1 FAIL |
| MUT-021 | CELL-021 | D-V15-IDEMPOTENCY | no-op permission short-circuit removed | policy OIDs recreated | 19 OK, 1 FAIL |
| MUT-022 | CELL-022 | D-V151-RANGES | users label CHECK always satisfied | MAC/MIC/category 23514 refusals | 22 OK, 3 FAIL |
| MUT-023 | CELL-022 | D-V151-RANGES | migration clamps to 62 instead of 63 | carol/dora clamp, re-issued ceiling | 22 OK, 3 FAIL |
| MUT-024 | CELL-023 | D-PERF-ENVELOPE | 2 ms injected into `_ctx_valid()` | all four envelope thresholds | 5 OK, 4 FAIL |
| MUT-025 | CELL-024 | D-CLAIM-LEDGER | C-01 cites a non-existent test ID | command exits 1 with L3/L4 errors | exit 1 |

Unmutated baselines on the same stand: `test_v191_fixes.py` 22 OK,
`test_v16_guards.py` 45 OK, `test_v17_events.py` 54 OK,
`test_v15_ceiling_trigger.py` 20 OK, `test_v15_security.py` 17 OK,
`test_v15_idempotency.py` 20 OK, `test_v151_ranges.py` 25 OK,
`test_perf_envelope.py` 9 OK. `test_side_channels.py` 5 OK / 2 GAP.

## Findings

1. **Mutation coverage is complete for the detectors that exist.** Before the
   batch, 0 of 27 detectors could be shown to fail. Now 24 have a fixture and
   3 have an explicit exemption; the registry has no "not verified" CL2
   warning left.

2. **CELL-002 is not mutation-testable at the repository layer.** The F8
   refusal comes from the platform's membership semantics, not from extension
   code: on the Astra stand `F8b` reports "platform blocks" and the extension's
   `ddl_guard` GRANT/REVOKE branch never fires (PostgreSQL does not raise the
   role-membership event trigger for global role objects). On true vanilla
   PostgreSQL 15 the platform allows the grant, so the same detector would fail
   without any code change. The cell keeps `tested` and an explicit
   `mutation_exemption`.

3. **CELL-027 and CELL-029 are not repository-level code guards.** The FK probe
   exercises a core PostgreSQL trigger that the suite creates itself, and the
   `pg_stats` cell is a catalog-privilege configuration control. Mutating
   extension SQL cannot move either verdict. Both carry a
   `mutation_exemption`, not a fake fixture.

4. **F3 and F4 share one fail-closed branch.** Deleting the
   `IF NOT v_matched_alter OR v_unresolved_alter` branch in `ddl_guard()` makes
   F3a, F3b, F4a and F4b fail together, because unqualified targets do not
   resolve under the guard's `search_path` and therefore rely on that branch.
   The fixtures instead mutate the dangerous-subcommand list, which isolates
   CELL-019 from CELL-020. This is a detector-structure finding: two cells are
   not independently falsifiable through the branch they share.

5. **`test_v191_fixes.py` is not runnable on a truly fresh cluster.** Its
   `make_roles()` runs before the SQL is installed and creates roles
   `IN ROLE rbac_admin`, so `rbac_admin` and `rbac_label_admin` must already
   exist. On a cluster where the extension was never installed the suite stops
   at `role "rbac_admin" does not exist`. This is a reproducibility gap in the
   suite, not in the extension. The runner's `--ensure-roles` performs the
   prerequisite idempotently.

6. **Two deployment paths need two contracts.** `test_fstek.py` deploys via
   `CREATE EXTENSION` and therefore reads `pg_config --sharedir`, not the
   working tree. Sharedir fixtures install the mutated copy into a writable
   extension directory and restore the previous bytes in a `finally` block.
   All other suites read `sql/` from the copied tree directly.

7. **CELL-016's tenant half is not exercised by the suite.** MUT-019
   neutralises the MAC comparison and two assertions fail. The suite seeds
   tenant 1 rows only, so removing the tenant predicate would leave every
   assertion green: the tenant half of this detector is asserted by the
   mutation, not by a contrasting row. This is a detector gap in
   `setup/test_v15_security.py`; the target repository was not modified.

8. **CELL-017's F2c assertion is vacuous.** MUT-020 disables the ownership
   check, but only F2b fails. The trap table has no row, so `set_object_label`
   stops with `Object ... key=1 not found` (P0001) before the row-level
   `BEFORE UPDATE` trigger can fire; F2c passes without observing anything.
   The fixture proves the confused-deputy refusal, not the unregistered-table
   path named in the cell limitation.

9. **CELL-011 needs two fixtures because it has two detectors.** MUT-014
   falsifies the FSTEC F14 assertion on 1.9.1; MUT-016 falsifies the
   branch-coverage suite on 1.5. One fixture cannot stand in for the other:
   the suites deploy different artifacts and assert different branches.

10. **CELL-022 needs a fresh-install and a migration fixture.** MUT-022
    disables the `users` label CHECK; MUT-023 clamps migrated MAC values to 62.
    The first does not touch the migration path, and the second does not touch
    direct INSERT validation.

11. **MUT-012 records the full I2 cascade, not a trimmed set.** The I1 guard
    mutation also breaks F13c (inherited role extraction) and F14a
    (`auth_epoch`), and F14a is the real I2 revocation. Trimming those failures
    would hide that the guard is load-bearing for the revoke path.

12. **The obvious AUTH_FAILURE mutation makes the control crash.** MUT-011
    targets unlock isolation (F11b). Mutating the lockout threshold instead
    makes F11a open a session, and the unguarded F11d control then crashes the
    suite; the failure set is no longer a clean sensitivity proof.

13. **Removing the role-upsert `WHERE` alone does not break idempotency.** The
    first MUT-021 revision dropped the change-detection guard from the role
    upsert. The suite stayed at 20 OK because the ceiling trigger itself
    compares old and new values and returns early when they match: the two
    guards are independently sufficient for the epoch half. The fixture now
    removes the no-op permission short-circuit, which recreates policies and
    fails the "policy OIDs unchanged" assertion. This is a useful negative
    result about where the invariant is enforced.

14. **HMAC repetition stays below the performance envelope.** The first
    MUT-024 revision repeated the memoized HMAC eleven times, expecting the
    v1.7 cost to return. One pgcrypto HMAC measures about 0.6 µs on this stand,
    so eleven of them add ~6 µs; the suite stayed at 9 OK. The v1.7 cost came
    from payload rebuild and SPI calls, not from the HMAC primitive. The
    fixture now injects a fixed 2 ms delay into `_ctx_valid()`; all four
    thresholds fail. It proves the envelope is tied to the measurement, but it
    is a latency injection, not a faithful reproduction of the old payload
    path.

15. **Failure parsing must read the plain summary.** Inline `[FAIL]` lines
    append a free-form detail, and assertion names contain colons
    (`F7f канал 2: ...`), so splitting on the first colon truncates them. The
    runner reads the list after `ИТОГО`/`ИТОГ`. `test_v15_ceiling_trigger.py`
    and `test_v151_ranges.py` print the list with no `Провалены:` header;
    `test_perf_envelope.py` prints only inline lines and uses ` -- ` as the
    detail separator, so MUT-024 opts into stripping that suffix before the
    exact comparison.

## Environment

Recorded run:

- PostgreSQL 15.17 (Debian 15.17-astra.se2.3r2) on Astra Linux.
- Relocated `tools/stand.sh` prefix at `/tmp/opencode/pgmut`, port 55434,
  trust auth; run as the `postgres` user.
- `rbac_pg` at commit `492f23c`.
- Artifact hashes pinned in `mutations.yaml`; a drifted artifact fails the
  preflight instead of silently mutating nothing.

Bring up a stand and run:

```sh
cd /home/admini/projects/rbac_pg
CITADEL_STAND_DIR=/tmp/opencode/pgmut \
CITADEL_STAND_PORT=55434 tools/stand.sh up

cd /home/admini/projects/dev-sec-skills
python3 spec/pilots/rbac_pg/mutations/run_mutations.py \
    --target /home/admini/projects/rbac_pg \
    --dsn "postgresql://postgres@127.0.0.1:55434/postgres" \
    --ensure-roles \
    --sharedir /tmp/opencode/pgmut/usr/share/postgresql/15/extension
```

Exit code 0 means every fixture failed exactly where predicted. Exit code 1
means at least one fixture did not match; the runner prints missing and
unexpected failures and writes the full suite output to
`<workdir>/results/<fixture>.log`. Exit code 2 means a tool or preflight
error.

Useful flags: `--only MUT-003` (repeatable), `--skip-baseline` (faster when
the unmutated suites are already known green), `--workdir PATH`, `--sharedir
PATH`.

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
6. If no repository source mutation can move the verdict, add a
   `mutation_exemption` with the mechanism and scope instead of a fixture.
   `cell_lint` reports it as info, not as an unverified warning.

## Remaining gaps

- CELL-028 has no detector at all (the `secure_table` FK contract is a recorded
  GAP), so there is nothing to mutate.
- No fixture targets the FSTEC migration M-series, `test_v16_guards.py` M1, or
  `test_v17_events.py` M1–M4; MUT-023 covers only 1.5 → 1.5.1.
- The CELL-016 tenant predicate and the CELL-017 unregistered-table path are
  asserted by no fixture (see findings 7 and 8).
- MUT-024 is a latency injection; it does not reproduce the exact v1.7 payload
  rebuild.
- Concurrency and multi-session ordering remain outside the mutation set,
  matching the limitations recorded in the registry.
