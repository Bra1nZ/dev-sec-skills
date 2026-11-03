# Tenant Isolation Review: `invoices` and `update_invoice`

## Verdict

The design does not enforce tenant isolation on its production path. The RLS policy is plausible, but it is unreachable: the application connects as the table owner with `BYPASSRLS`, and the only write path is a `SECURITY DEFINER` function that executes as that same owner. PostgreSQL therefore skips row security for every production query. The tests pass because they exercise a separate non-owner role, a path production never uses. That is worse than no RLS, because it creates false assurance.

There are three independent failures: an exempt runtime role, an exempt definer function, and a tenant identity taken from a client-controlled header. Fixing any one does not fix the other two.

## Invariant map

| Invariant | Current enforcement | Status |
|---|---|---|
| I1. `tenant_id` is `NOT NULL`, immutable after insert, and indexed | Not stated | Gap |
| I2. Tenant identity comes from an authenticated principal, never request data | `app.tenant_id` comes from a request header | Broken |
| I3. Tenant context is scoped to exactly one transaction/request | Likely session-level `SET`; pooling behavior unstated | Broken/unknown |
| I4. Every runtime query is subject to RLS | Runtime role owns the table and has `BYPASSRLS` | Broken |
| I5. All access paths use the same boundary: function, direct SQL, batch, views, partitions | Only the table policy exists; function bypasses it | Broken |
| I6. A write is authorized against the target row's tenant, not just the caller's context | Function updates by `invoice_id` alone | Broken |
| I7. Missing, malformed, or null context fails closed | Cast errors help, but custom GUCs are user-settable and fallback logic is unspecified | Partial |
| I8. Definer functions are hardened: pinned `search_path`, least privilege, no `PUBLIC` execute | Runs as table owner; defaults likely apply | Broken |
| I9. Cross-tenant references, uniqueness, and sequence leakage are prevented | Unspecified | Gap |
| I10. Audit records attribute the real tenant and actor | Header-derived, so spoofable | Broken |

The core invariant should be stated positively: for every request, all rows read or written must satisfy `row.tenant_id = authenticated_tenant`, and the authenticated tenant must be derived only from a verified identity or an explicitly authorized batch scope.

## Bypasses

**1. Owner plus `BYPASSRLS`.** `ENABLE ROW LEVEL SECURITY` does not apply to the table owner unless `FORCE ROW LEVEL SECURITY` is also set. A role with `BYPASSRLS` bypasses RLS even when the table is forced. The application therefore has two independent exemptions. The runtime role must be a non-owner without `BYPASSRLS`, and the owner must be a separate `NOLOGIN` DDL role. If the application must retain ownership, `FORCE` plus removal of `BYPASSRLS` is the minimum, but ownership still permits disabling policies.

**2. The `SECURITY DEFINER` function is a privileged oracle.** The function runs with the owner's privileges. Inside it, `current_user` is the owner, so every statement sees and updates every tenant's rows. Any caller who can execute the function receives that power for the SQL it performs. This is a confused deputy, not an isolation boundary.

**3. Default execute privilege.** PostgreSQL grants `EXECUTE` on new functions to `PUBLIC` by default. Unless explicitly revoked, every role in the database can call `update_invoice`, including roles that have no direct table access. The function must revoke `PUBLIC` and grant execute only to the application role.

**4. The header is not an identity.** A caller with a valid token for tenant A can send `X-Tenant: B`; if the function trusts the header, it acts for B. Proxies may strip, duplicate, or normalize headers, and internal callers may forward user-controlled values. Batch input rows are equally untrusted: the tenant ID in each row is data supplied by the caller, not proof that the caller may act for that tenant. Custom GUCs such as `app.tenant_id` are also settable by any session, so SQL injection anywhere in the application can switch tenants. The GUC can carry context, but it cannot be the authorization decision.

**5. The update predicate is not tenant-scoped.** `UPDATE invoices SET ... WHERE id = invoice_id` relies entirely on RLS to add the tenant condition. With the definer owner bypassing RLS, the ID alone selects the row. Even under a correct role, the function should include `AND tenant_id = authenticated_tenant` and reject a zero-row result; a `tenant_id` in the payload must be ignored or rejected, never applied.

**6. Session context leaks through pooling.** A session-level `SET app.tenant_id = ...` persists until changed or reset. On a pooled connection, a later request that fails before setting its own tenant can inherit the previous tenant and read or write that tenant's data. Error paths, timeouts, nested calls, and retries all create windows for bleed. `SET LOCAL` is safe only inside an explicit transaction; under autocommit it disappears immediately. The design needs a transaction-scoped context and a guaranteed reset, tested through the actual pooler.

**7. Policy coverage is incomplete by default.** Multiple permissive policies combine with `OR`, so one `USING (true)` policy anywhere on the table exposes everything. Policies have `TO` role lists; a policy that does not cover the runtime role yields default deny, which is safe, but the owner path bypasses it entirely. `FORCE` can be turned off by a migration. Partitions require their own policies for direct partition access; inheritance children and materialized views need separate treatment. Views before PostgreSQL 15 execute as their owner and can bypass RLS unless `security_invoker` is set. The definer function may also be vulnerable to `search_path` hijacking because its `search_path` is not pinned.

**8. Non-row and side-channel paths.** `TRUNCATE` is not filtered by RLS, so privileges must deny it. Foreign-key checks run with owner privileges and bypass RLS, allowing cross-tenant references or existence leaks through constraint errors. Global unique indexes can conflict across tenants or reveal that a value exists elsewhere. Sequences reveal volume. `COPY`, analytics roles, read replicas, backups, admin sessions, and `SET ROLE` all need the same scrutiny. If the application role can assume the owner role, RLS is again optional.

## Fail-open and wrong-tenant behavior

The design has several distinct failure modes that are often conflated:

- **Missing context:** `current_setting('app.tenant_id')` without `missing_ok` raises an error, which is fail-closed but becomes an availability problem. With `missing_ok = true` it returns `NULL`; `tenant_id = NULL` yields no rows for reads, which is also fail-closed. However, `tenant_id IS NOT DISTINCT FROM NULL` would match a nullable tenant column, and `COALESCE(current_setting(...), tenant_id)` is explicitly fail-open. Tenant columns must be `NOT NULL`, and policies must not use null-tolerant comparisons.
- **Malformed or empty context:** an empty string cast to `uuid` raises an error. If application code catches that and retries with a broader query or an owner connection, the policy becomes bypassable in practice. Error handling must never fall back to a more privileged path.
- **Wrong tenant:** pool leakage returns another tenant's rows rather than all rows. This is still a breach and should be classified as fail-open for isolation purposes.
- **Policy semantics:** a permissive `USING (true)` policy, a policy restricted to the wrong role, or an `ALL` policy with a missing `WITH CHECK` all undermine the intended predicate. `FOR UPDATE` and `RETURNING` must be tested, not assumed.
- **Function drift:** `ALTER FUNCTION ... OWNER TO` a bypassing role silently restores the bypass. The same is true for granting execute to `PUBLIC` again, or changing `SECURITY DEFINER` to an owner with broader privileges.

## Tests required before claiming isolation

**Test as the production principal.** Every test must run as the exact login role, through the same pooler and through `update_invoice`, not as a separate test role. A test role that differs in ownership or `BYPASSRLS` proves nothing about production. Add a mutation check: temporarily disable RLS, remove `FORCE`, or drop the policy, and confirm the suite fails. A suite that still passes is theater.

**Catalog and permission assertions.** Assert that `current_user` is not the table owner, is not superuser, and has `rolbypassrls = false`; that `pg_class.relrowsecurity` and `relforcerowsecurity` are both true; that the policy list contains no permissive `USING (true)` and covers the intended commands and roles; that the function has `prosecdef = true`, a pinned `search_path`, and no `PUBLIC` execute; that the runtime role has only the required grants; and that the owner role cannot log in.

**RLS authorization matrix.** For tenants A and B with rows in both, test `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `RETURNING`, aggregates, and `WHERE id = <other tenant>` for: same tenant allowed; cross tenant denied or zero rows; missing context; null context; empty string; malformed UUID; context set to A and then B in the same transaction; and context changed mid-request. Verify exact affected-row counts and returned rows. Test `TRUNCATE` is denied.

**Function and API tests.** Authenticated as A with header A and target invoice B: rejected. Header B with a token for A: rejected, with the header ignored or validated against the token, never trusted. Missing, duplicate, or conflicting header: rejected. Payload containing `tenant_id` of B: rejected or ignored. Own invoice: exactly one row updated. Caller without execute privilege: denied. Caller with a hostile `search_path` or hostile objects in a writable schema: no effect.

**Context lifecycle and concurrency.** Run interleaved A/B requests through the real pooler, including transaction-pooling mode, and assert no bleed. Force errors and timeouts mid-request, then issue a request with no context and confirm it fails closed rather than inheriting the prior tenant. Check `current_setting` after commit and rollback, and test nested function calls and triggers that might overwrite context.

**Batch job tests.** Reject rows whose tenant does not match the job's authorized scope; reject missing tenant; test mixed-tenant batches, duplicate invoice IDs across tenants, a victim invoice ID inside another tenant's row, failure midway with retry, and idempotent replay. Verify that a partial failure cannot commit one tenant's changes under another tenant's context, and that audit records name the correct tenant.

**Coverage and side-channel tests.** Direct partition access, views without `security_invoker`, materialized views, inheritance children, cross-tenant foreign keys, tenant-scoped uniqueness, sequence values, error messages, `EXPLAIN`, exports, read replicas, and admin tooling. Add CI catalog checks for policy and grant drift, and a migration test that fails if `FORCE` is removed, the policy is dropped, or the function owner changes.

## Minimum remediation

Use a non-owner runtime role without `BYPASSRLS`; enable `FORCE` RLS; derive tenant identity from the verified principal, not a header; bind it with `SET LOCAL` inside a transaction; make the function `SECURITY INVOKER` where possible, otherwise give it a hardened definer role, pinned `search_path`, revoked `PUBLIC` execute, and an explicit tenant predicate plus `WITH CHECK`; authorize batch rows against a job-scoped allowlist; and add composite tenant foreign keys and tenant-scoped unique constraints. Then prove the suite fails when isolation is deliberately broken.
