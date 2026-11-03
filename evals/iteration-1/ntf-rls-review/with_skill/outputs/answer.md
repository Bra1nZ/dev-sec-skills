# Review: invoices RLS UPDATE policy — negative-first test plan

## Verdict

**The current plan does not cover the claim.**

Claim under review:

> Only `tenant_admin` may update invoices, and only invoices in its own tenant.

Current evidence:

| ID | Existing test | What it actually proves |
| --- | --- | --- |
| T-POS-1 | `tenant_admin` can update its own invoice | A happy path. It can pass with the policy missing, with the test running as the table owner, with `BYPASSRLS`, or as a superuser. It does not assert the new value or that the policy was involved. |
| T-READ-1 | A `SELECT` by another tenant returns no rows | A read-isolation check. It says nothing about `UPDATE`; the `UPDATE` policy could be `USING (true)` and this test would still be green. It can also pass because the fixture is empty, because there is no `SELECT` policy (which makes the table look empty to that role), or because a `SELECT` policy—not the `UPDATE` policy—filtered the row. |

There is **no test that attempts a cross-tenant UPDATE**. Under the skill's rule, a security claim with no negative test is not partially covered—it is unchecked. T-POS-1 is positive-only; T-READ-1 is the wrong command for this claim.

**Coverage: 0 of 8 update-related claims covered; 1 read claim positive-only. 2 tests exist, 0 valid negative UPDATE tests.**

A green suite here is compatible with every one of these defects:

- any `tenant_admin` can update any tenant's invoice;
- any authenticated user with `UPDATE` privilege can update invoices;
- a `tenant_admin` can move an invoice into another tenant;
- the table owner, a view owner, a `SECURITY DEFINER` function, or a direct partition access bypasses RLS;
- a migration or extension upgrade drops/weakens the policy;
- the tenant context is client-settable, so `tenant_admin` A can set tenant B.

---

## 1. What must be true

The claim is only meaningful if all of these hold. Each is a separate mechanism and needs its own negative test.

1. **Role gate:** the principal has the `tenant_admin` role/grant (database role membership, policy `TO`, or an explicit grant row). Role membership alone must not be enough if the product requires an explicit tenant/object grant.
2. **Tenant gate:** the row's `tenant_id` equals the tenant bound to the authenticated session, and that binding cannot be chosen by the caller.
3. **Update gate:** `USING` decides which existing rows may be updated; `WITH CHECK` decides whether the new row may exist. Both are required; a `WITH CHECK` defect can move a row to another tenant.
4. **Read gate:** in PostgreSQL, an `UPDATE` target row must also be visible through the `SELECT` policy. A narrow `SELECT` policy can hide an over-broad `UPDATE` policy. Tests must isolate the layers.
5. **Connection gate:** RLS is enabled and forced; the application does not connect as the table owner, a superuser, or a `BYPASSRLS` role.
6. **No alternate path:** views, `SECURITY DEFINER` functions, upserts, `MERGE`, partitions, inheritance children, triggers, `COPY`, pooled GUCs, and `TRUNCATE` do not provide a write path around the policy.
7. **No partial write:** every refused update leaves the row, audit trail, outbox, and derived state unchanged.
8. **Migration preserves it:** fresh install, upgrade, downgrade, ownership changes, table recreation, partition attachment, and restore preserve the property on live data.

The test matrix below assumes this policy shape only to make the SQL concrete. If the production policy uses a different tenant source or role model, keep the matrix and substitute names; do not reduce the classes of actors or paths.

```sql
CREATE POLICY invoices_update_tenant_admin ON invoices
  FOR UPDATE
  TO tenant_admin
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

## 2. Claim map

This table is the index. Every row needs a living test; a hole in this index is a hole in coverage.

| ID | Claim | Mechanism to verify | Existing evidence | Required negative tests (minimum) | Status |
| --- | --- | --- | --- | --- | --- |
| C1 | Only a principal holding `tenant_admin` may `UPDATE` invoices. | `GRANT UPDATE` + RLS policy `TO tenant_admin` / role membership. | T-POS-1, positive only. | N01, N05, N10, N11, N12, N13, N14, N15, N23, N24 | **UNCOVERED** |
| C2 | A `tenant_admin` may update only rows whose `tenant_id` equals its own tenant. | `UPDATE ... USING (tenant_id = session_tenant)`. | None. T-READ-1 is a `SELECT`, not this claim. | N01, N02, N03, N04, N05, N06, N07, N16, N17 | **UNCOVERED** |
| C3 | An `UPDATE` cannot move a row to another tenant or set `tenant_id` to `NULL`. | `WITH CHECK` (and the `SELECT` policy's new-row check). | None. | N08, N09, N21, A05, A06 | **UNCOVERED** |
| C4 | A refused update leaves no partial write or side effect. | Statement atomicity, triggers, app transaction, audit/outbox. | None. | N21, S01, S02, S03, S04, S05 | **UNCOVERED** |
| C5 | Role membership is not a substitute for an explicit tenant/object grant; admin-without-grant is denied. | Grant table / ACL check in the policy, or table/column privilege. | None. Requirement is ambiguous. | N14, N15, N24 | **OPEN / ASSUMPTION** |
| C6 | RLS cannot be bypassed by the connection principal or configuration. | `ENABLE`/`FORCE ROW LEVEL SECURITY`, non-owner app role, no `BYPASSRLS`, no `PUBLIC`/permissive policy. | None. | N22, N23, A16, A17, A18 | **UNCOVERED** |
| C7 | No alternate write path writes across tenants. | Views, functions, upsert, `MERGE`, partitions, triggers, `COPY`, pooled context. | None. | A01–A15, A19 | **UNCOVERED** |
| C8 | Migration/upgrade preserves the property. | Migration chain, extension upgrade, live-data rerun, introspection. | None. | M01–M08 | **UNCOVERED** |
| C9 | Cross-tenant `SELECT` returns no rows. | RLS `SELECT` policy. | T-READ-1, positive only; weak (no own-row control, no privilege check, no fixture control). | T-READ-1 own-row positive control, A12 (`COPY TO`) | **POSITIVE ONLY / DOES NOT COVER UPDATE** |

CSV form for the audit ledger:

```csv
claim_id,claim,mechanism,required_tests,status
C1,Only tenant_admin may UPDATE invoices,GRANT + RLS policy TO tenant_admin,"N01;N05;N10;N11;N12;N13;N14;N15;N23;N24",UNCOVERED
C2,tenant_admin may UPDATE only own-tenant rows,RLS UPDATE USING tenant predicate,"N01;N02;N03;N04;N05;N06;N07;N16;N17",UNCOVERED
C3,UPDATE cannot move a row to another tenant,RLS UPDATE WITH CHECK,"N08;N09;N21;A05;A06",UNCOVERED
C4,Refused UPDATE leaves no partial write,Atomicity + triggers + audit/outbox,"N21;S01;S02;S03;S04;S05",UNCOVERED
C5,Admin-without-grant is denied,Explicit tenant/object grant,"N14;N15;N24",OPEN-ASSUMPTION
C6,RLS cannot be bypassed by connection/config,ENABLE/FORCE RLS + non-owner app role,"N22;N23;A16;A17;A18",UNCOVERED
C7,No alternate write path crosses tenants,Views/functions/upsert/MERGE/partitions/COPY/pool,"A01-A15;A19",UNCOVERED
C8,Migration/upgrade preserves the property,Migration chain + live-data rerun,"M01-M08",UNCOVERED
C9,Cross-tenant SELECT returns no rows,RLS SELECT policy,"T-READ-1 positive control;A12",POSITIVE-ONLY
```

Status rule used here: `UNCOVERED` means no test attempts the violation. `POSITIVE ONLY` means a happy path exists but no negative exists. `OPEN / ASSUMPTION` means the requirement itself is not defined widely enough to claim. Nothing in this plan is marked covered until the negative, the postcondition, the mutation check, and the migration rerun all pass.

---

## 3. Review of the two existing tests

### T-POS-1: `tenant_admin` updates its own invoice

Keep it, but it is only a control; it is not evidence for C1/C2. Add:

- **Harness guard:** assert `current_user` is not `rolsuper`, not `rolbypassrls`, and not the table owner; assert `row_security = on`.
- **Positive assertion:** assert the command tag is `UPDATE 1` and the row's `amount`/`status` actually changed; then verify the row as the owner from a separate connection.
- **Policy-present check:** assert the policy exists, is `FOR UPDATE`, includes the intended role, and has a real `WITH CHECK`. If the test passes with the policy dropped, it proves nothing.
- **Negative sibling:** immediately run N01 (other tenant's `tenant_admin` updates this row) and assert `UPDATE 0` plus an unchanged row.

### T-READ-1: other-tenant `SELECT` returns no rows

Keep it for the read claim, but fix the confounders:

- Positive control: same role can `SELECT` its own invoice and sees exactly 1 row.
- Privilege control: role has `SELECT` on the table; otherwise the query may fail with a grant error, which is not a row-isolation result.
- Fixture control: the other tenant's invoice exists and is visible to the owner.
- Classification: `SELECT 0` under RLS is not an error. Record that no SQLSTATE was raised and that the row is unchanged.
- Do not use this test as evidence for the `UPDATE` policy. Add N03 to test `UPDATE ... RETURNING`: it must return 0 rows, and the row must remain unchanged.

---

## 4. Test environment and fixtures

### Actors

| Actor | Membership / grant | Tenant context | Purpose |
| --- | --- | --- | --- |
| `app_ta_a` | `tenant_admin` for A | A | Authorized positive control; context-forgery attacker. |
| `app_ta_b` | `tenant_admin` for B | B | Cross-tenant attacker against A; positive control against B. |
| `app_tu_a` | `tenant_user` A (neighboring role) | A | Must not update. |
| `app_tv_a` | `tenant_viewer` / support A | A | Must not update. |
| `app_auth_a` | authenticated, no tenant role | A | Must not update. |
| `app_admin_unscoped` | `tenant_admin` role, no tenant binding / no explicit grant | none or arbitrary | Admin-without-grant / unbounded admin. |
| `app_admin_revoked` | `tenant_admin` role, grant expired/revoked | A | Role membership must not outlive the grant. |
| `app_ta_col` | `tenant_admin` A with `UPDATE(amount)` but not `UPDATE(tenant_id)` | A | Column-level/object-level access, not table-level policy. |
| `app_anon` | no login role / no tenant membership | none | Role-less session. |
| `app_owner` | table owner / migration role | n/a | Expected bypass unless `FORCE RLS`; never an application role. |
| `app_bypass` | test-only `BYPASSRLS` | n/a | Proves the test can detect a bypass; never grant to an application role. |

If the real model uses per-tenant roles (`tenant_admin_a`, `tenant_admin_b`), keep the same matrix and substitute the role names. Do not collapse the tenants into one global role without testing role membership separately.

### Fixtures

Use fixed, non-secret UUIDs (no real credentials):

- `inv_a1`, `inv_a2` — tenant A, amounts 100 and 200, status `open`.
- `inv_b1`, `inv_b2` — tenant B, amounts 300 and 400.
- Optional nullable-tenant row and a soft-deleted row only if the schema allows them; otherwise test the `NOT NULL` constraint separately.
- The table is owned by `app_owner`; enable RLS and **force** it:

```sql
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;
```

- In the isolated RLS fixture, `GRANT SELECT, UPDATE ON invoices TO app_ta_a, app_ta_b, app_tu_a, app_tv_a, app_auth_a;` so that a `0` row result cannot be mistaken for a grant denial. Then repeat the relevant tests without the grant to classify the grant layer separately.
- Do not grant `TRUNCATE` or `DELETE` to application roles unless the product explicitly intends those operations; test them as separate claims.
- The test runner must not itself run as the table owner or superuser. If it must use a superuser to `SET ROLE`, the guard below is mandatory.

### Harness guard

```sql
DO $$
DECLARE
  is_super boolean;
  is_bypass boolean;
  is_owner boolean;
BEGIN
  SELECT r.rolsuper, r.rolbypassrls
    INTO is_super, is_bypass
    FROM pg_roles r
   WHERE r.rolname = current_user;

  SELECT c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
    INTO is_owner
    FROM pg_class c
   WHERE c.oid = 'public.invoices'::regclass;

  IF is_super OR is_bypass OR is_owner THEN
    RAISE EXCEPTION
      'RLS harness is vacuous: current_user=% super=% bypass=% owner=%',
      current_user, is_super, is_bypass, is_owner;
  END IF;

  IF current_setting('row_security') <> 'on' THEN
    RAISE EXCEPTION 'row_security is not on: %', current_setting('row_security');
  END IF;
END $$;
```

Run every DML test inside a transaction, under `SET LOCAL ROLE`, with a transaction-local tenant setting, then roll back:

```sql
BEGIN;
SET LOCAL ROLE app_ta_b;
SELECT set_config('app.tenant_id', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', true);
-- test statement
ROLLBACK;
```

The owner-side verification must use a separate connection or a clearly separated `RESET ROLE`; do not verify the "unchanged" state through the same RLS-filtered role that was supposed to be denied. A filtered `SELECT` returning zero rows is not proof that the row did not change.

---

## 5. P0 negative tests (release-blocking)

Write N01–N17 and N20–N24 first. N18/N19 are positive controls used to validate the harness, not the leading evidence. All tests are executed as the stated actor, in a transaction that is rolled back. `0` means `UPDATE 0` with no error. `42501` means the PostgreSQL SQLSTATE for insufficient privilege; assert the message to distinguish the RLS check from a grant/ownership check. Every expected refusal must include the postcondition checks from section 7.

| ID | Actor / context / target | Statement | Expected | Postcondition / classification |
| --- | --- | --- | --- | --- |
| **N01** | `app_ta_b`, context B, specific `inv_a1` by ID | `UPDATE invoices SET amount = amount + 1 WHERE id = inv_a1;` | `UPDATE 0` | `inv_a1` unchanged; this is the headline missing test: cross-tenant UPDATE, not SELECT. |
| **N02** | `app_ta_b`, context B, all A rows | `UPDATE invoices SET amount = amount + 1 WHERE tenant_id = A;` | `UPDATE 0` | A row count and values unchanged. |
| **N03** | `app_ta_b`, context B, `inv_a1` | `UPDATE ... WHERE id = inv_a1 RETURNING *;` | `UPDATE 0`; 0 returned rows | No A data leaks through `RETURNING`; row unchanged. |
| **N04** | `app_ta_b`, context B, `inv_a1` via join/subquery | `UPDATE invoices i SET amount = i.amount + 1 FROM (VALUES (inv_a1)) v(id) WHERE i.id = v.id;` | `UPDATE 0` | Row unchanged. Also test `WHERE id IN (SELECT id FROM invoices WHERE tenant_id = A)` as B: 0. |
| **N05** | `app_ta_a`, context A, specific `inv_b1` by ID | `UPDATE invoices SET amount = amount + 1 WHERE id = inv_b1;` | `UPDATE 0` | B row unchanged. |
| **N06** | `app_ta_a`, context A, `inv_b1` | `UPDATE invoices SET tenant_id = A WHERE id = inv_b1;` | `UPDATE 0` | B row unchanged; cannot steal another tenant's row into A. |
| **N07** | `app_ta_b`, context B, `inv_a1` | `UPDATE invoices SET tenant_id = B WHERE id = inv_a1;` | `UPDATE 0` | A row unchanged; cannot steal A's row into B. If this returns `UPDATE 1`, the `USING`/`WITH CHECK` combination is broken. |
| **N08** | `app_ta_a`, context A, own `inv_a1` | `UPDATE invoices SET tenant_id = B WHERE id = inv_a1;` | `42501` (new row violates RLS) | A row unchanged; cannot move its own row out of A. This specifically attacks `WITH CHECK`. |
| **N09** | `app_ta_b`, context B, own `inv_b1` | `UPDATE invoices SET tenant_id = A WHERE id = inv_b1;` | `42501` | B row unchanged; cannot move its own row into A. |
| **N10** | `app_tu_a` (tenant_user), context A, `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `0` (with UPDATE grant in fixture); otherwise `42501` permission denied | Row unchanged. If no grant, this is a GRANT refusal, not RLS; say so. |
| **N11** | `app_tv_a` (viewer/support), context A, `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `0` or `42501` | Row unchanged; classify the layer. |
| **N12** | `app_auth_a` (authenticated, no tenant role), context A, `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `0` or `42501` | Row unchanged; role-less/tenant-role-less session must not update. |
| **N13** | `app_anon` (role-less), no context, `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `42501` permission denied | Row unchanged. Repeat with `GRANT UPDATE` to PUBLIC or to `app_anon` in a test copy to isolate RLS; if the update then succeeds, RLS is not protecting this role. |
| **N14** | `app_admin_unscoped` (`tenant_admin` role, no tenant binding or explicit grant), target `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `0` / `42501` | Admin-without-grant must be denied. If it can set context A and succeeds, role membership alone is over-granting; add an explicit grant/tenant check to the policy. |
| **N15** | `app_admin_revoked` (role still present, tenant/object grant revoked or expired), target former `inv_a1` | `UPDATE ... WHERE id = inv_a1;` | `0` / `42501` | Row unchanged. If it succeeds, role membership outlives the grant; the policy must check the live grant, not just the role. If per-object grants are out of scope, record that as an explicit limitation. |
| **N16** | `app_ta_a`, deliberately sets context B, target `inv_b1` | `SET LOCAL app.tenant_id = B; UPDATE ... WHERE id = inv_b1;` | Expected `0` | **Architecture blocker if `UPDATE 1`.** A client-settable GUC is not an authenticated tenant binding. If the app role can set it, any `tenant_admin` can change tenant context and update B. Use a signed/derived context or per-tenant DB roles; if not, the "own tenant" claim is false for direct DB access. |
| **N17** | `app_ta_a`, missing / empty / whitespace / malformed context, target `inv_a1` | Four separate statements: `RESET app.tenant_id`; `SET app.tenant_id = ''`; `SET app.tenant_id = '   '`; `SET app.tenant_id = 'not-a-uuid'` | `42704` / `22P02` / `0` depending on implementation; never `UPDATE 1` | Row unchanged. Classify platform-cast refusal vs policy refusal; both are fail-closed but they are not the same evidence. |
| **N18** | `app_ta_a`, context A, own `inv_a1` | `UPDATE invoices SET amount = amount + 1 WHERE id = inv_a1;` | `UPDATE 1` | Positive control; amount changed; owner sees it. Without this, a wall of `0`s may just mean the role cannot see any rows. |
| **N19** | `app_ta_b`, context B, own `inv_b1` | Same as N18 on B | `UPDATE 1` | Symmetry control; B's admin is not globally denied. |
| **N20** | `app_ta_a`, context A, both A rows | `UPDATE invoices SET amount = amount + 1 WHERE tenant_id = A;` | `UPDATE 2` | Many/boundary case; both A rows changed. |
| **N21** | `app_ta_a`, context A, two A rows, one moves to B | `UPDATE invoices SET tenant_id = CASE WHEN id = inv_a2 THEN B ELSE tenant_id END WHERE id IN (inv_a1, inv_a2);` | `42501`; statement fails | Both rows unchanged; a single failing row must not leave a partial write. |
| **N22** | `app_ta_a`, context A, target `inv_b1` | `SET LOCAL row_security = off; UPDATE ... WHERE id = inv_b1;` | `42501` "query would be affected by row-level security policy" | Row unchanged. For a non-bypass role, this is a platform guard, not a policy expression. Superuser/`BYPASSRLS` expected to bypass; test only to document the boundary. |
| **N23** | `app_ta_a` attempts to become another tenant's admin | `SET LOCAL ROLE app_ta_b;` | `42501` | No role switch. If it succeeds, the role membership graph allows cross-tenant escalation; inspect `pg_auth_members`. |
| **N24** | `app_ta_col` with column-level `UPDATE(amount)` but not `UPDATE(tenant_id)`, context A, `inv_a1` | `UPDATE invoices SET tenant_id = B WHERE id = inv_a1;` followed by `UPDATE invoices SET amount = amount + 1 WHERE id = inv_a1;` | First: `42501` column/table privilege; second: `UPDATE 1` | This is object-level access, not table-level policy. The first refusal is a column privilege, not RLS; record that distinction. |

If the tenant context is not a GUC, run the same violation against the actual source: tamper with the tenant header, JWT claim, path tenant, or session function. The class is "caller chooses the tenant"; the mechanism differs. A test that only changes a GUC that production does not use is not coverage.

Object-level access, not just table-level policy: N01/N05 target a specific invoice ID; N14/N15 test role membership without the required grant; N24 tests column-level privilege; A18 checks the effective ACL/policy catalog. Do not satisfy this requirement by asserting only that a policy row exists in `pg_policies`.

### Minimum set if time is limited

If only a small window exists, run **N01, N02, N05, N07, N08, N09, N10, N12, N14, N16, N21, N22**, plus **M01/M02** and **V01/V02**. Even that set does not make the full claim; it only removes the most obvious false greens.

---

## 6. Layer isolation: do not let the SELECT policy hide a broken UPDATE policy

PostgreSQL behavior that matters for this plan:

- An `UPDATE` target row must be visible through the `SELECT` policy. With only an `UPDATE` policy and no `SELECT` policy, even an authorized own-tenant update returns `UPDATE 0`.
- Permissive policies are OR'ed. A duplicate `FOR ALL TO PUBLIC USING (true)` policy makes the new tenant policy ineffective.
- A narrow `SELECT` policy can hide a broken `UPDATE USING` policy: the cross-tenant update returns `0` because the row is not visible, not because the `UPDATE` policy filtered it.
- A narrow `SELECT` policy can also hide a broken `WITH CHECK`: the new row fails the `SELECT` policy's new-row check, producing `42501`, even if the `UPDATE` policy's `WITH CHECK` is `true`.

Therefore, every `0`/`42501` result needs a layer attribution. Use two configurations:

1. **Production configuration:** run N01–N24 exactly as the application runs. Record the observed result and the policy catalog. This is what users get.
2. **Isolation configuration (test-only, disposable DB):** widen the `SELECT` policy so the actor can see both A and B, leaving the production `UPDATE` policy in place. Then:
   - `app_ta_a` updating `inv_b1` must be `UPDATE 0` if the `UPDATE USING` is tenant-scoped; `UPDATE 1` means `USING` is too broad (V03).
   - `app_ta_a` updating `inv_a1` to `tenant_id = B` must be `42501` if `WITH CHECK` is tenant-scoped; success means `WITH CHECK` is missing/too broad (V02).
3. **Mutation configuration:** replace `WITH CHECK` with `true` / `USING` with `true` and show the corresponding test fails (section 11). A test that cannot fail is not coverage.

Do not run isolation/mutation changes against a shared or production database. Use a disposable test database, or a transaction that is guaranteed to roll back, and restore the policy.

A concrete isolation setup looks like this (test-only):

```sql
BEGIN;

-- Make both tenants' rows visible so a SELECT policy cannot mask the UPDATE policy.
DROP POLICY IF EXISTS invoices_select_tenant ON invoices;
CREATE POLICY invoices_select_test_wide ON invoices
  FOR SELECT TO app_ta_a, app_ta_b
  USING (tenant_id IN ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                       'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'));

-- Keep the production UPDATE policy in place.
SET LOCAL ROLE app_ta_a;
SELECT set_config('app.tenant_id', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', true);

UPDATE invoices SET amount = amount + 1 WHERE id = '...b1...';  -- expect UPDATE 0
UPDATE invoices SET tenant_id = '...b...' WHERE id = '...a1...'; -- expect 42501

ROLLBACK;
```

If the first statement returns `UPDATE 1`, the `UPDATE USING` expression is not tenant-scoped. If the second succeeds, `WITH CHECK` is not enforcing the new tenant. Both are release blockers even if the production configuration's narrow `SELECT` policy happened to return `0`.

---

## 7. Refusal classification and no partial write

### Refusal classification table

Assert the SQLSTATE, the message family, the current role, and the policy/privilege layer. "Something failed" is not evidence that the rule ran.

| Observed result | SQLSTATE | Layer | What it proves | Required handling |
| --- | --- | --- | --- | --- |
| `UPDATE 0`, no error | none | RLS `USING` filtered, `SELECT` policy filtered, no matching row, or missing `SELECT` policy | Does not identify which mechanism ran. | Assert row unchanged; run positive control; use isolation configuration to attribute. |
| `new row violates row-level security policy` | `42501` | RLS `WITH CHECK` or the `SELECT` policy's new-row check | The new row was rejected. | Isolate `WITH CHECK` with a wide `SELECT`; record which check fired. |
| `permission denied for table invoices` | `42501` | Table/column `GRANT` or ownership | The actor never reached the policy. | Do not count as RLS coverage. Grant `UPDATE`/`SELECT` in a test copy to reach the policy, then retest. |
| `unrecognized configuration parameter "app.tenant_id"` | `42704` | Missing tenant context; `current_setting` without `missing_ok` | Fail-closed at the context lookup. | Test missing context separately; do not treat as policy evidence. |
| `invalid input syntax for type uuid` | `22P02` | Malformed tenant context cast | Platform/cast refusal. | Test malformed/empty context separately; assert no row changed. |
| `COPY FROM not supported with row-level security` | `0A000` | PostgreSQL platform | RLS blocks this bulk path; defense in depth. | Record platform refusal; do not claim your policy expression ran. |
| `query would be affected by row-level security policy` after `SET row_security = off` | `42501` | PostgreSQL RLS guard | A non-bypass role cannot disable RLS. | Test as a platform guard; superuser/`BYPASSRLS` are outside the app model. |
| `NOT NULL violation` / `CHECK constraint` | `23502` / `23514` | Schema constraint | The policy may not have been reached. | Classify separately; fix the test so the policy check is the one being exercised. |
| `UPDATE 1` / `MERGE 1` on another tenant's row | none | **Failure** | Cross-tenant write occurred. | Stop; do not pass go. Investigate `USING`, `WITH CHECK`, role, and path. |
| `TRUNCATE TABLE` success | none | ACL, no RLS | RLS does not apply to `TRUNCATE`. | Revoke `TRUNCATE`; treat as a separate destructive-path finding. |
| `SET ROLE` to another tenant's admin succeeded | none | Role membership | Cross-tenant escalation. | Remove membership; test `pg_auth_members`; treat as a finding. |

### No partial write and no side effects

After **every** expected refusal, verify from an owner/second connection:

- `amount`, `status`, `tenant_id`, `updated_at`, and `xmin` are unchanged (or compare a row hash). `updated_at` alone is insufficient if a trigger updates it.
- The number of rows for each tenant is unchanged.
- `RETURNING` returned zero rows.
- Audit/outbox/webhook/notification tables have no new rows attributable to the attempt.
- Sequences used by the statement did not advance.
- Statement-level triggers did not enqueue work on an `UPDATE 0`.
- A multi-row statement that fails on one row leaves **all** rows unchanged (N21).
- The application does not turn a failed transaction into a successful response; a failed statement aborts the transaction (`25P02` on reuse) and must be rolled back, not reused.
- If audit is a claimed property, test both channels: the row/audit table inside the transaction and a server log/audit channel that survives rollback. A refusal that leaves no evidence may be acceptable, but do not claim audit coverage without testing it.

| ID | Postcondition check | Assertion |
| --- | --- | --- |
| S01 | Row state | Before/after hash of `amount`, `status`, `tenant_id`, `updated_at`, `xmin` matches; query as owner. |
| S02 | Derived state | Audit/outbox/webhook/event counts and sequence values unchanged. |
| S03 | Statement-level side effects | An `UPDATE 0` did not enqueue work through a statement trigger. |
| S04 | Atomicity/transaction | Multi-row failure leaves every row unchanged; a failed transaction is not reused or committed. |
| S05 | Concurrency | A cross-tenant update racing an authorized update cannot win or move the row; repeat with two sessions. |

Example runner pattern (test-only):

```sql
BEGIN;
SET LOCAL ROLE app_ta_b;
SELECT set_config('app.tenant_id', '...b...', true);

DO $$
DECLARE n integer;
BEGIN
  UPDATE invoices SET amount = amount + 1 WHERE id = '...a1...';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 0 THEN
    RAISE EXCEPTION 'N01 failed: cross-tenant UPDATE affected % rows', n;
  END IF;
END $$;

ROLLBACK;

-- Separate owner connection:
SELECT amount, tenant_id, updated_at, xmin
  FROM invoices WHERE id = '...a1...';
-- Assert the values match the pre-test snapshot.
```

Do not run the postcondition query as `app_ta_b`; RLS will hide the row and produce a false "unchanged."

---

## 8. Alternate paths

Every one of these must be attempted as the cross-tenant `tenant_admin` (and as `tenant_user` where relevant), not just inspected in a catalog. If an object/path does not exist in this deployment, record it as `N/A` with the schema reason and do not count it as covered; do not silently skip it. If the path exists in production, it is not `N/A`.

| ID | Path | Why it can bypass or evade the policy | Test | Expected / finding |
| --- | --- | --- | --- | --- |
| A01 | View with `security_invoker = true` | Base-table RLS is evaluated as the invoker. | Create `invoices_v` with `WITH (security_invoker = true)`; `app_ta_b` updates `inv_a1` through the view. | `UPDATE 0`; row unchanged. |
| A02 | View owned by the table owner, default `security_invoker = false` | Runs with the view owner's privileges; owner bypasses RLS unless `FORCE`. | Same as A01 without `security_invoker`; test with `FORCE RLS` on and off. | With `FORCE` on: 0. Off: `UPDATE 1` in a local PG17 reproduction. Fix with `security_invoker = true` or `FORCE`; treat as a finding. |
| A03 | `SECURITY DEFINER` function | Runs as the function owner, often the table owner. | `GRANT EXECUTE` to `app_ta_b`; function does `UPDATE invoices ...`; capture `ROW_COUNT`, not just the function's return value. | With `FORCE`: 0 rows changed. Without `FORCE`: 1 row changed in a local PG17 reproduction. A function returning `1` unconditionally must not be trusted; assert the row. |
| A04 | `SECURITY INVOKER` function | Runs as caller; base RLS should apply. | Same call with an invoker function. | `UPDATE 0`; row unchanged. |
| A05 | `INSERT ... ON CONFLICT DO UPDATE` (upsert) | The conflict branch is an UPDATE path and also involves `INSERT` policies/privileges. | As `app_ta_a`, insert `inv_b1`'s ID with tenant A and `ON CONFLICT (id) DO UPDATE SET amount = ...`. | No change to B's row; observed PG17: `42501` when policies exist. Test with and without an `INSERT` policy; without `INSERT` privilege, `42501 permission denied` is not RLS evidence. |
| A06 | `MERGE` (PG15+) | Contains UPDATE actions; must honor `UPDATE` policy. | As `app_ta_a`, `MERGE` targeting `inv_b1`. | No change; test own-row positive control. |
| A07 | Parent partitioned table | Parent policy applies through the parent. | As `app_ta_b`, update `inv_a1` through `invoices` parent. | `UPDATE 0`; row unchanged. |
| A08 | Direct child partition | Parent RLS does not automatically enable RLS on the child; direct access can bypass. | As `app_ta_b`, `UPDATE invoices_a_... WHERE id = inv_a1;`. | Must be 0. A local PG17 reproduction returned `UPDATE 1` when the child had `relrowsecurity = false`. Enable RLS/`FORCE` on every partition or revoke direct child access. |
| A09 | Inheritance child | Same as partition; direct child access has its own RLS setting. | Same as A08 on the child table. | 0; otherwise finding. |
| A10 | Trigger function | A `SECURITY DEFINER` trigger can write another tenant's rows while handling an allowed update. | Fire an allowed update on A; check B rows and audit/outbox. | B unchanged. Pin `search_path`; do not let a trigger run as owner without checks. |
| A11 | `COPY FROM` | Bulk write path; PostgreSQL may refuse it under RLS or it may bypass executor checks. | As `app_ta_a`, `COPY invoices ... FROM STDIN` with a B row. | Observed PG17: `0A000` "COPY FROM not supported with row-level security." If accepted, assert no cross-tenant write; treat as a write path. |
| A12 | `COPY TO` | Read path; must apply `SELECT` policy. | As `app_ta_b`, `COPY invoices TO STDOUT`. | Only B rows. Observed PG17: only B row. |
| A13 | `TRUNCATE` | RLS does not apply; only ACL. | As `app_ta_a`, `TRUNCATE invoices;` with and without `TRUNCATE` grant. | `42501` without grant; with grant it succeeds and wipes all tenants. Revoke `TRUNCATE` from application roles; separate destructive-path claim. |
| A14 | `DELETE` | Separate policy/claim; a `FOR ALL` policy or DELETE grant may allow cross-tenant deletion. | As `app_ta_a`, `DELETE FROM invoices WHERE tenant_id = B;`. | `0`/`42501`; B rows unchanged. Do not assume the UPDATE policy covers DELETE. |
| A15 | Pooled connection / GUC leak | `SET` (session) persists across pool checkout; `SET LOCAL` does not. | Session A sets tenant A, returns to pool; session B acquires the same physical connection and updates without resetting. | Must be denied. Use `DISCARD ALL`/`RESET ALL` on checkout; test both `SET` and `SET LOCAL`. If B sees A's context, cross-tenant update is possible. |
| A16 | Table owner / superuser / `BYPASSRLS` | These bypass RLS by design (owner only without `FORCE`). | As `app_owner` with `FORCE` on; as `app_bypass`; as superuser. | `FORCE` owner: 0; without `FORCE`: 1; bypass role/superuser: 1. Document as outside app model and assert application roles lack these attributes. |
| A17 | `SET row_security = off` | A non-bypass role gets an error; a bypass role/owner may turn RLS off. | N22; repeat as owner and `BYPASSRLS`. | Non-bypass: `42501`; owner/bypass: expected bypass. Do not use a bypass role as the application role. |
| A18 | Policy catalog and effective permissions | A correct-looking test can coexist with a `PUBLIC`/`ALL` permissive policy, wrong `polroles`, missing `WITH CHECK`, or missing grant. | Query `pg_policies`, `pg_class`, `pg_roles`, `information_schema.role_table_grants`; run `has_table_privilege`/`has_column_privilege` for every actor. | Exactly the intended `FOR UPDATE` policy for the intended roles; no `PUBLIC` or duplicate permissive `ALL` policy; `WITH CHECK` not `true`; no `BYPASSRLS`; owner not the app role; no `PUBLIC` grants. Catalog checks are necessary but not sufficient; pair with N01/N08. |
| A19 | App entry points | RLS is the last line; the API may use a definer function, batch job, import, or worker that bypasses it. | `PATCH /invoices/:id`, bulk update, GraphQL mutation, CSV import, queue worker, admin console; test with tenant A credentials against B's invoice and with a forged tenant header/JWT. | Denied at the app layer and at the DB layer; no partial write. If only direct SQL is tested, do not claim API/batch coverage. |

---

## 9. Migrations and upgrades

Run the negative suite **after every migration on a copy of live data**, not only on a fresh empty database. A migration that silently widens permissions is a regression with a green release note.

### M01 — Fresh install

Apply the full migration chain to an empty database, create A/B fixtures, and run N01–N24, A01–A19 and the positive controls. Assert policy presence and behavior.

### M02 — Upgrade with live data

Take a pre-upgrade snapshot with A/B rows (including any legacy/NULL-tenant rows), apply the upgrade, and rerun the same suite. Compare per-tenant counts and row hashes before/after; the migration itself must not move invoices across tenants.

### M03 — Policy duplication and idempotence

Apply the migration twice / apply an upgrade over an older policy. Assert exactly one effective permissive `UPDATE` policy for the intended roles. If an old `FOR ALL TO PUBLIC USING (true)` or a duplicate tenant policy survives, N01/N08 must catch the widening. Do not rely on `CREATE POLICY` succeeding; inspect `pg_policies`.

### M04 — Owner, rename, or table recreation

If a migration changes the table owner, recreates/renames the table, or swaps a view/function owner, assert `relrowsecurity`, `relforcerowsecurity`, `relowner`, policies, grants, and views/functions all point at the new relation. If the app role becomes the owner, `FORCE RLS` is mandatory.

### M05 — Downgrade/rollback

Run the down migration and test again. Two acceptable outcomes:

- fail closed: RLS remains enabled and the policy denies cross-tenant updates; or
- explicitly documented rollback behavior with a compensating control.

If the down migration disables RLS or drops the policy without replacement and cross-tenant updates then succeed, that is a release blocker, not a rollback detail.

### M06 — Partition/inheritance attachment

After attaching a new partition/child, run A07/A08/A09. The child must have RLS enabled/forced; the parent policy is not enough for direct child access. Repeat after every partition-creation migration.

### M07 — Backfill and data migration

Any migration that updates `tenant_id` or copies invoices must be tested with counts/checksums per tenant. Run it as the migration owner, not as an application role; owner bypass is expected for DDL, but the data changes must be constrained. Test the app role immediately after the backfill.

### M08 — Supported platform matrix and restore

Rerun the negative suite on every supported PostgreSQL major version (for example 14–17 if that is the support claim), because RLS behavior, `MERGE` (15+), and view `security_invoker` (15+) vary. Also restore from a dump and rerun: policies, grants, view options, and function ownership must survive `pg_dump`/`pg_restore`.

### Catalog assertions

Run these before and after each migration:

```sql
SELECT c.relrowsecurity, c.relforcerowsecurity, c.relowner::regrole
  FROM pg_class c
 WHERE c.oid = 'public.invoices'::regclass;

SELECT polname, polcmd, polroles::regrole[],
       pg_get_expr(polqual, polrelid)      AS using_expr,
       pg_get_expr(polwithcheck, polrelid) AS check_expr
  FROM pg_policy
 WHERE polrelid = 'public.invoices'::regclass
 ORDER BY polname;

SELECT grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema = 'public' AND table_name = 'invoices'
 ORDER BY grantee, privilege_type;

SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
  FROM pg_roles
 WHERE rolname LIKE 'app_%'
 ORDER BY rolname;
```

Assertions:

- `relrowsecurity = true`; `relforcerowsecurity = true` if the owner is not a separate migration-only role.
- The intended `FOR UPDATE` policy exists, is not `TO PUBLIC`, and has a non-trivial `WITH CHECK`.
- There is no duplicate/legacy permissive `ALL` policy and no `PUBLIC` grant.
- `app_*` roles are not superuser, not `BYPASSRLS`, and not the table owner.
- Views are `security_invoker=true` or owned by a role that is itself constrained by `FORCE RLS`.
- Every partition/child has its own RLS state tested, not inferred from the parent.

---

## 10. Verifier tests: prove the tests can fail

A passing negative test is only evidence if it fails when the mechanism is removed. Run these on a disposable database or inside a rolled-back transaction.

| ID | Mutation | Expected mutation result | What it proves |
| --- | --- | --- | --- |
| V01 | `ALTER TABLE invoices DISABLE ROW LEVEL SECURITY;` then N01 as `app_ta_b` against `inv_a1`. | N01 must **fail** (cross-tenant UPDATE returns `UPDATE 1`). Restore. | N01 actually detects RLS, not a missing row or a role without privilege. |
| V02 | Replace the `UPDATE` policy with `USING (tenant_id = A)` and `WITH CHECK (true)`; widen `SELECT` to see both tenants; run N08 (`SET tenant_id = B`). | N08 must **fail** (update succeeds). Restore. | N08 actually tests `WITH CHECK`, not the `SELECT` policy. |
| V03 | Replace `UPDATE USING` with `USING (true)`; widen `SELECT`; run N05/N01 variant (`app_ta_a` updates `inv_b1`). | N05 must **fail** (`UPDATE 1`). Restore. | N05 actually tests `UPDATE USING`, not the narrow `SELECT` policy. |
| V04 | Compare production narrow `SELECT` vs wide `SELECT` for the same UPDATE. | With narrow `SELECT`, a broken `UPDATE` policy can still produce `0`; with wide `SELECT`, it produces `1`. | Proves why `0` alone is not evidence and why layer isolation is required. |
| V05 | Revoke `UPDATE` from `app_ta_b`; run N01. | N01 now fails with `42501 permission denied`, not `UPDATE 0`. | Proves the suite distinguishes the grant layer from RLS. If it was counted as RLS coverage before, that was false. |
| V06 | Remove the row / point at a non-existent ID and run N01. | N01 still returns `0`; it must not be counted as coverage of cross-tenant isolation without a fixture-existence guard. | Proves the need for a positive control and a fixture assertion. |

A test artifact is not evidence that the test can fail. Record the mutation command and the observed failure in the evidence file.

---

## 11. Evidence ledger and release gate

### Per-test evidence record

```csv
test_id,claim_id,pg_version,commit,migration,actor,context,target,statement,expected,observed_sqlstate,rows_affected,post_state_hash,artifact,verdict
N01,C2,17.11,abc1234,0042,app_ta_b,B,inv_a1,update by id,UPDATE 0,,0,sha256:...,tests/rls/n01.log,PASS
N08,C3,17.11,abc1234,0042,app_ta_a,A,inv_a1,set tenant_id=B,42501,42501,0,sha256:...,tests/rls/n08.log,PASS
N16,C2,17.11,abc1234,0042,app_ta_a,B,inv_b1,forged context,UPDATE 0,,1,sha256:...,tests/rls/n16.log,FAIL-BLOCKER
```

Record command, result, artifact path, commit, environment, exact scope, and the role actually used. Keep failed/negative results visible; do not delete a failing case because the suite must stay green.

### Release gate

- **Do not claim the policy works** from T-POS-1 or T-READ-1 alone.
- C1/C2/C3 may be marked covered only after N01–N24, the layer-isolation checks, V01–V03, and M01/M02 pass on the actual application role and a migrated live-data copy.
- If N16 succeeds (forged tenant context), C2 is **false**, not "partially covered." Fix the tenant source: signed/derived context, per-tenant database role, or a policy that does not trust a client-settable GUC.
- If A02/A03/A08/A15/A16 succeed, C1/C2 are false for those paths. Fix with `FORCE RLS`, `security_invoker`, function-side tenant checks, child-partition RLS, and pool reset; or state the exact scope and residual risk. Do not imply completeness.
- If only direct SQL was tested, do not claim API, batch-import, worker, admin-console, or migration coverage.
- Partial truth is acceptable only when it is labeled partial. "0 rows on one SELECT" is not a tenant-isolation guarantee.

**Current release status: not ready. 0/8 update claims covered; 2 existing tests, both insufficient; at least 24 core negatives, 19 alternate-path checks, 8 migration checks, and 6 verifier checks are missing.**

---

## Appendix: PostgreSQL 17 behavior notes used in this plan

These were reproduced locally on PostgreSQL 17.11 with a policy of the shape `UPDATE ... USING (tenant_id = current_setting('app.tenant_id')::uuid) WITH CHECK (tenant_id = ...)`, `FORCE RLS`, and non-owner roles. Rerun on the supported matrix; do not treat these as evidence for a different deployment.

| Case | Observed behavior |
| --- | --- |
| Cross-tenant UPDATE by ID (`app_ta_b` -> A row) | `UPDATE 0`; row unchanged. This is the test missing from the current plan. |
| Own-tenant UPDATE with no `SELECT` policy | `UPDATE 0` even though the `UPDATE` policy allows the row. A `SELECT` policy is needed for the target row. |
| `WITH CHECK` violation (`tenant_id` -> another tenant) | `ERROR 42501`: "new row violates row-level security policy". |
| `WITH CHECK (true)` with a wide `SELECT` policy | `UPDATE 1`: proves the test can catch a broken `WITH CHECK`. |
| `SET row_security = off` as a non-bypass role | `ERROR 42501`: "query would be affected by row-level security policy". |
| `COPY FROM` into an RLS table | `ERROR 0A000`: "COPY FROM not supported with row-level security". |
| `COPY TO` as tenant B | Only B rows; `SELECT` RLS applies. |
| Table owner without `FORCE` | `UPDATE 1`; owner bypasses. |
| View owned by table owner without `FORCE` | `UPDATE 1`; view owner path bypasses. |
| `SECURITY DEFINER` function owned by table owner without `FORCE` | `UPDATE 1`; test `ROW_COUNT`, not the function's return value. |
| Direct child partition with parent RLS but child `relrowsecurity = false` | `UPDATE 1`; direct child access bypasses the parent policy. |
| `SET app.tenant_id = B` as tenant A's admin | `UPDATE 1` against B's row in this policy shape; a client-settable GUC is not an authenticated tenant binding. Treat as a blocker unless the role cannot set the context. |
| Cross-tenant upsert `ON CONFLICT DO UPDATE` | `ERROR 42501`; no change to the other tenant's row. |
| `MERGE` cross-tenant | `MERGE 0`; no change. |
| `TRUNCATE` with the privilege granted | Succeeds; RLS does not apply. Revoke it from application roles. |
