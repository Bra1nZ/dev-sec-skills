# Review: PostgreSQL RLS test plan for `invoices`

## Verdict

The plan is not sufficient to support the claim "only `tenant_admin` can update invoices in its own tenant." It contains one positive UPDATE test and one cross-tenant SELECT test. The SELECT test does not exercise the UPDATE policy, and neither test excludes a same-tenant non-admin update, a cross-tenant UPDATE, a `WITH CHECK` bypass, tenant-context spoofing, or a privileged/alternate write path.

The suite can be green with an insecure policy. For example, this passes the two current tests if a separate SELECT policy hides other tenants:

```sql
CREATE POLICY invoices_update
ON invoices
FOR UPDATE
TO PUBLIC
USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Any role in tenant A, not just `tenant_admin`, can update tenant A rows. That is the central gap.

## 1. Specification gaps to resolve first

The phrase "only tenant_admin can update invoices in its own tenant" is underspecified. The claim map must distinguish these questions, because each has different tests:

1. **What is `tenant_admin`?** A database role, a membership row, or an application/JWT claim? A single global `tenant_admin` database role cannot by itself scope an admin to one tenant.
2. **What defines "own tenant"?** A session GUC such as `app.tenant_id`, a membership table keyed by the current user, or a JWT claim? A client-settable GUC is not an authorization boundary unless the role predicate independently constrains the tenant.
3. **Can an UPDATE change `tenant_id`?** If not, the policy needs a `WITH CHECK` that rejects cross-tenant and `NULL` values.
4. **What is the expected denial behavior?** A row filtered by `USING` produces `UPDATE 0` with no error. A new row rejected by `WITH CHECK` produces SQLSTATE `42501`. Tests must assert the correct one; "expect an error" is wrong for an invisible row.
5. **Are INSERT/DELETE/TRUNCATE in scope?** A non-admin with DELETE+INSERT can effectively replace a row even if UPDATE is blocked. The claim is UPDATE-specific, but the security review should state whether that is acceptable.
6. **Are table owner, superuser, and `BYPASSRLS` in scope?** They bypass RLS unless the table is owned by a forced-RLS role and even `FORCE` does not affect superusers or `BYPASSRLS`. The application role must not be any of these.

## 2. What the current tests prove

| Test | What it actually exercises | What it does not prove |
|---|---|---|
| `tenant_admin` updates own invoice | The happy path and the UPDATE grant for one actor/row | That non-admins are denied; that other tenants are denied for UPDATE; that `WITH CHECK` is correct; that the policy is not overly broad |
| SELECT by another tenant returns no rows | At most, read isolation for that actor | Nothing about UPDATE; it can pass because of a SELECT policy, missing SELECT privilege, a view/filter, or a fixture that does not contain the row |

An additional weakness: the cross-tenant SELECT test is vacuous if the target row does not exist. Every negative test should first confirm, using an owner/privileged connection, that the target row exists and has the expected values. It should then confirm after the attempt that the row is unchanged.

## 3. Required negative tests

Use separate login roles, not a superuser using `SET ROLE`. Run each test in its own transaction. Verify both the command result and the post-state through a privileged fixture connection. Placeholder fixtures:

- Tenant A invoice `A1` (`id = 1001`, `tenant_id = A`)
- Tenant B invoice `B1` (`id = 2001`, `tenant_id = B`)
- `admin_a` = tenant admin for A only
- `user_a` = ordinary user in A
- `admin_b` = tenant admin for B only
- `anon` = login role with only the grants being tested

### 3.1 Core actor/tenant matrix

| ID | Actor | Action | Expected result |
|---|---|---|---|
| N01 | `user_a` (same tenant, non-admin) | `UPDATE invoices SET amount = amount + 1 WHERE id = 1001` | `UPDATE 0`; `A1` unchanged. Do **not** require `42501`; invisible rows are silently skipped. |
| N02 | `user_a` | Same UPDATE with `RETURNING *` | Zero rows returned and no column values leaked. |
| N03 | `admin_b` | `UPDATE invoices ... WHERE id = 1001` | `UPDATE 0`; `A1` unchanged. This is the missing UPDATE counterpart to the existing SELECT test. |
| N04 | `admin_b` | Bulk `UPDATE invoices SET ...` with no tenant predicate | Only B rows are affected; `A1` unchanged. |
| N05 | `anon` / no login role | UPDATE `A1` | `42501` permission denied if no grant; if granted, `UPDATE 0`; never a change. |
| N06 | role with UPDATE grant but no admin membership | UPDATE own-tenant row | `UPDATE 0`, unchanged. Proves the grant alone is insufficient. |
| N07 | `admin_a` | UPDATE `A1` (positive control) | `UPDATE 1`; value change visible through owner connection. Establishes that the test harness and role setup work. |

### 3.2 `WITH CHECK` and tenant reassignment

| ID | Action | Expected result |
|---|---|---|
| N08 | `admin_a` updates `A1` and sets `tenant_id = B` | SQLSTATE `42501` (new row violates RLS policy); transaction rolls back; `A1` remains in A. |
| N09 | `admin_a` updates `A1` and sets `tenant_id = NULL` (if nullable) | `42501` or NOT NULL/check violation; row unchanged. |
| N10 | `admin_a` updates `A1` with `tenant_id = A` (no-op tenant change) | `UPDATE 1`; this is a positive control for the `WITH CHECK`. |
| N11 | `admin_a` updates `A1` with a `WHERE` clause and `RETURNING`; attempts to move it to B | No row returned and no change; assert the error/rollback behavior is consistent. |
| N12 | `admin_b` updates `B1` and changes `tenant_id = A` | `42501`; `B1` remains in B. Cross-tenant movement must be blocked in both directions. |

If the policy has only `USING` and no explicit `WITH CHECK`, PostgreSQL uses the `USING` expression as the check for UPDATE. Still test it explicitly: a later policy edit that adds a permissive `WITH CHECK` is a real regression.

### 3.3 Tenant-context spoofing and role escalation

These are critical if the policy reads `current_setting('app.tenant_id')` or checks a global role.

| ID | Action | Expected result |
|---|---|---|
| N13 | `admin_a` executes `SET LOCAL app.tenant_id = 'B'`, then updates `B1` | `UPDATE 0`; `B1` unchanged. If this succeeds, the policy authorizes a tenant chosen by the client. |
| N14 | `user_a` sets `app.tenant_id = 'A'` and updates `A1` | `UPDATE 0`; changing the GUC must not grant the admin role. |
| N15 | Unset, reset, empty, or whitespace `app.tenant_id`; attempt UPDATE | Clean denial (`UPDATE 0` or a documented error such as `42704`/`22P02`); never all rows and never a default tenant. |
| N16 | Malformed UUID in `app.tenant_id` | `22P02` or clean denial; no data modification, no fallback to a privileged path. |
| N17 | Login role that is a member of the global `tenant_admin` role performs `SET ROLE tenant_admin`, then updates `B1` as a non-B admin | Must fail. Check `pg_auth_members`: a global admin role makes every member an admin for every tenant unless tenant scoping is independently enforced. |
| N18 | `admin_a` calls `set_config('app.tenant_id', 'B', false)` or uses a pooled connection that retains a prior session setting | Must not carry tenant A's context into tenant B, and must not inherit B's context from a previous checkout. Prefer `SET LOCAL` per transaction and reset pooled sessions. |
| N19 | `admin_a` attempts `SET SESSION AUTHORIZATION` / `SET ROLE` to the owner or another privileged role | `42501`; app roles must not be members of the table owner, superuser, or a `BYPASSRLS` role. |

If policy checks `current_user`, note that `SET ROLE` changes it. If it checks `session_user`, note that connection pooling and role switching can produce surprising results. The test plan should state which identity is authoritative.

### 3.4 Privilege and RLS-bypass paths

| ID | Check | Expected result |
|---|---|---|
| N20 | App role is table owner | Must be false. Ownership permits `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` and, without `FORCE`, bypasses RLS. |
| N21 | App role has `rolsuper` or `rolbypassrls` | Must be false. Both bypass RLS regardless of `FORCE`. |
| N22 | App role executes `SET row_security = off` | Must not bypass: expect an error if RLS would apply, or continued filtering; never an unfiltered UPDATE. |
| N23 | App role has `TRUNCATE` on `invoices` | Must be false. `TRUNCATE` is not row-level and is not governed by RLS. |
| N24 | App role has unintended INSERT/DELETE | Must be false, or those policies must be tested. DELETE+INSERT is an effective row-replacement path even when UPDATE is blocked. |
| N25 | App role has `pg_write_all_data` or is a member of another broad predefined role | Review membership; broad grants undermine the "only tenant_admin" claim even where RLS still applies. |
| N26 | App role has column-level UPDATE grants that include `tenant_id` | `tenant_id` must not be updateable by non-admin paths; test column grants as well as table grants. |
| N27 | App role can `ALTER TABLE`, `CREATE POLICY`, or `DROP POLICY` | Must be false. DDL requires ownership; verify ownership is a migration role, not an application role. |

### 3.5 Alternate SQL write paths

| ID | Path | Expected result |
|---|---|---|
| N28 | `INSERT ... ON CONFLICT (id) DO UPDATE` as `admin_b` targeting `A1` | `A1` unchanged. The UPDATE branch must apply the UPDATE `USING`/`WITH CHECK`; also verify the conflict path does not reveal that `A1` exists. |
| N29 | Same upsert as `user_a` targeting `A1` | `A1` unchanged. |
| N30 | `MERGE` (PostgreSQL 15+) as `admin_b` or `user_a` targeting `A1` | `A1` unchanged; MERGE must apply UPDATE/INSERT/DELETE policies. |
| N31 | Updatable view `v_invoices` over `invoices`, updated as `admin_b` or `user_a` | `UPDATE 0`/`42501`; no base-table change. Check the view is `security_invoker` where supported; pre-15 views execute with the view owner's privileges and can bypass the caller's RLS. |
| N32 | `SECURITY DEFINER` function that updates invoices | Executing as `user_a`/`admin_b` must not bypass RLS. A definer function runs as its owner; if the owner is the table owner without `FORCE RLS`, it can bypass. Audit every definer function that writes `invoices`. |
| N33 | `INSTEAD OF` trigger on an updatable view, or a definer trigger function | Must not perform an unguarded cross-tenant update; trigger functions run as their owner if `SECURITY DEFINER`. |
| N34 | Direct UPDATE of a partition / inheritance child as `admin_b` or `user_a` | Must be denied or filtered. Do not assume parent policies protect direct child access; assert `relrowsecurity` and `relforcerowsecurity` on every child and test direct access. |
| N35 | `COPY FROM invoices` under RLS | Verify behavior on the target PostgreSQL major version. If rejected, assert the documented error and that no rows are written; if accepted, assert INSERT policies apply. Do not treat COPY as an approved bypass. |
| N36 | FK `ON UPDATE CASCADE`, rule, or trigger originating from another table | Must not move or modify a tenant B invoice into tenant A (or vice versa). RI triggers and definer triggers are a common alternate write path. |
| N37 | `dblink`, foreign table, or logical replication path | App role must not have access. RLS is local to the table; remote/FDW and replication paths need separate review. |

### 3.6 Migration and schema invariants

Run these against the schema produced by the actual migrations, not a hand-built test fixture.

| ID | Invariant | Expected |
|---|---|---|
| N38 | `pg_class.relrowsecurity` for `invoices` | `true` |
| N39 | `pg_class.relforcerowsecurity` for `invoices` | `true`; otherwise the table owner bypasses RLS |
| N40 | Table owner | A migration/administration role, not an application login role; app role is not a member of it |
| N41 | `pg_policy` inventory | Exactly the intended UPDATE policy (plus explicitly reviewed SELECT/INSERT/DELETE policies). No unexpected permissive `ALL`/`UPDATE` policy; no `PUBLIC` role unless the policy's own predicate is role-restrictive |
| N42 | Policy expressions | Both `USING` and `WITH CHECK` constrain `tenant_id`; inspect `pg_get_expr(polqual, ...)` and `pg_get_expr(polwithcheck, ...)` after migration |
| N43 | Privileges | No UPDATE to `PUBLIC`; only intended app roles have UPDATE; no unintended column grants on `tenant_id` |
| N44 | Default privileges | `ALTER DEFAULT PRIVILEGES` does not grant broad UPDATE on future tables/partitions to app or public roles |
| N45 | Partitions/children | Every partition/child accessed directly has RLS enabled and forced, or the app role has no direct privilege on it |
| N46 | Migration ordering | RLS is enabled before grants/app traffic; no migration window where the table is writable without the policy |
| N47 | Idempotency/upgrade | Re-running migrations does not drop and recreate the policy with a broader definition; `DROP POLICY IF EXISTS` does not remove an unrelated policy |
| N48 | Down migration | Rolling back does not leave RLS disabled, leave a permissive policy, or leave broad grants behind; test the down/up cycle |
| N49 | Constraint design | `tenant_id` is `NOT NULL`; unique keys that are meant to be per-tenant include `tenant_id`; otherwise cross-tenant unique conflicts can leak existence or cause denial of service |

Inspection queries:

```sql
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
WHERE c.oid = 'invoices'::regclass;

SELECT polname, polcmd, polpermissive, polroles::regrole[],
       pg_get_expr(polqual, polrelid)        AS using_expr,
       pg_get_expr(polwithcheck, polrelid)   AS with_check_expr
FROM pg_policy
WHERE polrelid = 'invoices'::regclass;

SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_inherits i
JOIN pg_class c ON c.oid = i.inhrelid
WHERE i.inhparent = 'invoices'::regclass;

SELECT grantee, privilege_type, is_grantable
FROM information_schema.role_table_grants
WHERE table_name = 'invoices';

SELECT grantee, column_name, privilege_type
FROM information_schema.column_privileges
WHERE table_name = 'invoices';

SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles
WHERE rolname = current_user;
```

### 3.7 Leakage and oracle tests

| ID | Action | Expected |
|---|---|---|
| N50 | As `admin_b`, UPDATE `A1` by known id vs UPDATE a nonexistent id | Same command tag/error class; the caller cannot distinguish "exists in another tenant" from "does not exist." Do not rely on different error messages or row counts. |
| N51 | As `admin_b`, attempt an update that collides with a unique key on `A1` | No cross-tenant unique-conflict oracle. If invoice numbers are per-tenant, the unique index should include `tenant_id`. |
| N52 | Audit/trigger writes during a blocked UPDATE | No audit row containing another tenant's values; audit tables must not become a read side channel. |
| N53 | Blocked UPDATE with `RETURNING` | No row data returned. Check both `UPDATE 0` and empty result sets. |

## 4. Condensed test matrix

| Actor | Row | Operation | Expected |
|---|---|---|---|
| `admin_a` | `A1` | update non-tenant column | `UPDATE 1`; changed |
| `admin_a` | `A1` | set `tenant_id = B` | `42501`; unchanged |
| `admin_a` | `A1` | set `tenant_id = NULL` | `42501`/constraint error; unchanged |
| `user_a` | `A1` | update | `UPDATE 0`; unchanged |
| `admin_b` | `A1` | update | `UPDATE 0`; unchanged |
| `admin_b` | `B1` | update | `UPDATE 1`; changed |
| `admin_b` | `B1` | set `tenant_id = A` | `42501`; unchanged |
| `anon` | `A1` | update | `42501` or `UPDATE 0`; unchanged |
| `admin_a` with GUC `B` | `B1` | update | `UPDATE 0` or `42501`; unchanged |
| `admin_a` via view / upsert / MERGE / definer function | `B1` or `A1` | update | No unauthorized change |
| direct partition access as `user_a`/`admin_b` | partition row | update | Denied or filtered |
| app role | `invoices` | `TRUNCATE` | `42501` |
| app role | `invoices` | `SET row_security = off` | No bypass |

## 5. Claim map

Status: **C** = covered by existing tests, **P** = partially covered, **M** = missing.

| ID | Claim to establish | Evidence required | Tests | Status |
|---|---|---|---|---|
| C0 | The test harness itself is trustworthy | App role is not superuser/owner/`BYPASSRLS`; fixture row exists; privileged post-state check | N07, N20-N22, N38-N40 | M |
| C1 | A tenant admin can update an invoice in its own tenant | `UPDATE 1` and changed post-state | Existing positive test; N07 | C |
| C2 | A non-admin in the same tenant cannot update | `UPDATE 0` or `42501`; row unchanged; no `RETURNING` data | N01, N02, N06 | M |
| C3 | A tenant admin of another tenant cannot update the target invoice | UPDATE-specific test, not SELECT; row unchanged; fixture confirmed | N03, N04 | M (the existing SELECT test is not this claim) |
| C4 | An update cannot move a row to another tenant or to `NULL` | `WITH CHECK` rejects; row unchanged | N08-N12 | M |
| C5 | Bulk updates cannot cross tenant boundaries | Only own-tenant rows affected; other rows unchanged | N04 | M |
| C6 | Unauthenticated/no-privilege actors cannot update | `42501` or `UPDATE 0`; unchanged | N05 | M |
| C7 | Tenant context cannot be spoofed through GUC/session/role switching | Admin A with tenant B context still cannot update B; no default tenant; malformed context fails closed | N13-N19 | M |
| C8 | A global `tenant_admin` role does not grant admin rights in every tenant | `pg_auth_members` review; per-tenant scoping enforced independently of client context | N17, N41 | M (design risk) |
| C9 | Ownership, superuser, `BYPASSRLS`, and `row_security=off` cannot be used by the app | Role/ownership assertions; `SET row_security=off` test | N20-N22 | M |
| C10 | Alternate write paths cannot bypass the policy | Upsert, MERGE, views, definer functions, triggers, partitions, TRUNCATE, DELETE+INSERT, COPY | N28-N37 | M |
| C11 | Migrations permanently enforce the policy | RLS enabled+forced, exact policy expressions, grants, partitions, down/up cycle | N38-N49 | M |
| C12 | A blocked attempt changes nothing and leaks nothing | Post-state equality; consistent error/row-count behavior; no `RETURNING` or audit leak | N50-N53 plus every negative test | M |
| C13 | The existing cross-tenant SELECT test supports the UPDATE claim | It does not; it can pass via a SELECT policy or missing SELECT privilege | Existing SELECT test | M (invalid inference) |

**Minimum bar before merge:** C0, C2, C3, C4, C7, C9, C11, and C12. C8 and C10 are required if a global admin role or any alternate write path exists in production.

## 6. Migration review checklist

1. `ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;` is present and committed.
2. `ALTER TABLE invoices FORCE ROW LEVEL SECURITY;` is present when the table owner is not a dedicated, non-login admin role.
3. The table is owned by a migration/admin role; the application role neither owns it nor inherits from its owner.
4. The policy is explicitly `FOR UPDATE` (or `FOR ALL` with all commands reviewed); a permissive `FOR ALL` policy can widen UPDATE unexpectedly.
5. `TO` lists the intended role(s). `TO PUBLIC` is acceptable only if the policy predicate itself checks role membership, and even then the role/membership model must be reviewed.
6. `USING` and `WITH CHECK` both constrain the tenant, and `WITH CHECK` also prevents changing `tenant_id` to another tenant or `NULL`.
7. Tenant identity is derived from a trustworthy source. A client-settable GUC alone is not sufficient; pair it with a membership lookup or another server-side binding.
8. Revoke broad grants: no `UPDATE`/`INSERT`/`DELETE`/`TRUNCATE` to `PUBLIC` or unrelated roles; review default privileges and column grants.
9. Every partition/inheritance child has RLS enabled and forced, or the app role has no direct access; test direct child access.
10. No `SECURITY DEFINER` function, updatable view, or trigger provides an unguarded write path. Views should be `security_invoker` where supported.
11. The migration does not temporarily disable RLS or create the table without RLS before enabling it.
12. The down migration restores the prior security state; the up/down/up cycle does not leave a permissive policy or broad grant.
13. `tenant_id` is `NOT NULL`; per-tenant unique constraints include `tenant_id`.
14. Run the test suite against the migrated schema with roles created the same way production roles are created, not with a superuser connection or a fixture that bypasses RLS.

## 7. Expected SQLSTATEs and test semantics

- Cross-tenant row invisible to `USING`: `UPDATE 0`, no error. Assert unchanged post-state.
- New row violates `WITH CHECK`: SQLSTATE `42501`, transaction rolled back.
- Missing table privilege: SQLSTATE `42501`.
- Missing or malformed tenant GUC: documented error such as `42704` or `22P02`, or zero rows; never an all-tenant update.
- `SET row_security = off` as a non-owner subject to RLS: error or continued filtering; never a bypass.
- `TRUNCATE` by an unprivileged app role: `42501`; RLS does not protect against a role that has `TRUNCATE`.

Every negative test must assert two things: the command outcome **and** that the target row is unchanged. A test that only asserts "no error" or "zero rows" without a fixture-existence check can pass for the wrong reason.
