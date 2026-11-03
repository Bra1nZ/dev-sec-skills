# Tenant Isolation Review: `invoices` RLS and `update_invoice`

## Bottom line

The claimed control is not on the production path. `invoices` has RLS, but the application connects as the table owner with `BYPASSRLS`, so every query skips the policy. The `SECURITY DEFINER` function runs with the same owner's privileges, so it skips the policy too. The only actor that meets the policy is a test role absent from production; the passing suite proves the policy works for a role that never issues a production query, not that tenant isolation holds.

Two independent bypasses stack; either defeats the policy: the login role has `BYPASSRLS`, and the function is `SECURITY DEFINER` owned by the table owner (owners bypass RLS unless `FORCE`, and `BYPASSRLS` beats `FORCE`).

The design never states that `update_invoice` has an explicit `tenant_id` predicate, and setting `app.tenant_id` filters nothing by itself. If the body relies on the policy, `UPDATE ... WHERE id = invoice_id` reaches every tenant's rows. If a predicate exists, it is the real enforcement point and must be shown and tested.

The signature is `update_invoice(invoice_id, payload)`, yet the batch passes a tenant per row; either an unstated parameter exists or the batch sets the GUC itself, so the caller chooses the tenant.

## Invariant map

| ID | Invariant | Enforcement point | Failure mode | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| I-01 | Access requires a matching tenant; `tenant_id` is immutable | `tenant_id = $principal` in the `UPDATE` predicate plus `ROW_COUNT = 1`; RLS as a second layer | deny, no write | T-05, T-06, T-07 | all DML |
| I-02 | Tenant comes only from a verified principal | Auth binds tenant to session/token; function reads that binding, never a header | deny | T-16–T-19 | HTTP, batch, jobs |
| I-03 | No production path is owner or `BYPASSRLS` | `NOLOGIN` owner for DDL; `LOGIN` app role, `NOBYPASSRLS`, non-owner | connection denied | T-01, T-03 | prod, CI |
| I-04 | RLS enabled, forced, and covering every command | `ENABLE` + `FORCE`; `USING` and `WITH CHECK`; no permissive `true` policy | deny | T-02, T-29 | schema |
| I-05 | Context never leaks across requests | transaction-local `set_config(..., true)`; reset at txn start; `current_setting(..., false)` | abort | T-12–T-15 | pooled connections |
| I-06 | Missing, empty, or malformed context fails closed | validation at function entry; distinct error; no default | abort | T-08–T-11 | all callers |
| I-07 | Definer cannot be hijacked or over-privileged | pinned `search_path`; non-login, non-`BYPASSRLS` owner; `EXECUTE` revoked from `PUBLIC` | function error | T-20–T-23 | database |
| I-08 | Batch writes stay in the job's tenant scope | guard before the loop; per-row tenant checked; mixed input rejected | reject, rollback | T-24–T-26 | batch |
| I-09 | Mutations and denials are auditable and atomic | audit insert in same txn; append-only; app cannot edit the trail | abort mutation | T-31, T-33 | all writes |
| I-10 | Retries and concurrent updates are safe | version check in `UPDATE` predicate; idempotency key | conflict | T-27, T-32 | API, batch |

## Bypasses

**B1 (critical). Production role bypasses RLS.** `BYPASSRLS` outranks `FORCE ROW LEVEL SECURITY`; every statement on the application connection is unscoped. RLS is absent here, not defense in depth. Owner privileges also let any code path skip the function, so SQL injection or a compromised process gains cross-tenant table access.

**B2 (critical). `SECURITY DEFINER` re-bypasses RLS.** Even if the login role lost `BYPASSRLS`, the function executes as its owner. An owner bypasses RLS with `FORCE` unset, and a `BYPASSRLS` owner bypasses it even with `FORCE`. The function must be `SECURITY INVOKER` or owned by a role that is neither the table owner nor `BYPASSRLS`.

**B3 (critical). Tenant comes from a request header.** A header is client-controlled: `X-Tenant-Id: <victim>` writes that tenant's invoice when no identity binding exists. Tenant identity must come from the verified session or token; a header is a routing hint at most.

**B4 (high). Batch trusts the tenant in each input row.** A confused deputy: the batch credential has cross-tenant power and the input file chooses the target, so a mistyped or malicious row writes into another tenant. The batch principal needs an explicit tenant scope, checked per row before any write.

**B5 (high). GUC residue on pooled connections.** `SET` or `set_config(..., false)` survives `COMMIT` and returns to the pool, so the next request inherits the previous tenant. A per-row `set_config` inside one transaction leaves the last value for any later statement. `ALTER ROLE ... SET app.tenant_id` would give every session a default tenant.

**B6 (high). The GUC is caller-settable.** Any role with a connection can `SET app.tenant_id` to anything. A custom GUC is a label, not a claim: usable as transaction-local transport when bound from verified identity upstream and filtered explicitly, never as authorization.

**B7 (high). No explicit tenant predicate, and `ROW_COUNT` is unchecked.** `WHERE id = invoice_id` updates whichever tenant owns that UUID. A zero-row update reported as success is a silent no-op today and a plausible insert path tomorrow.

**B8 (medium). Unpinned `search_path` in a definer.** A schema earlier in the caller's path can shadow functions or operators used by the body, escalating to the definer's privileges. Pin the path and schema-qualify every object.

**B9 (medium). Payload mass-assignment.** If `payload` is merged into columns, it can carry `tenant_id` or `id` and re-tenant a row. Whitelist fields and add `WITH CHECK` so the database rejects a move too.

## Fail-open risks

- **Caught errors become allows.** `current_setting('app.tenant_id')` raises when unset, which is fail-closed only if the error propagates. A wrapper that retries without context, returns an empty success, or falls back to a default tenant turns this into an allow.
- **`current_setting(..., true)` returns NULL.** `tenant_id = NULL` is never true. Reads silently return an empty set, a success-shaped result that hides the failure; writes update zero rows.
- **Default-tenant fallback and header parsing.** A missing or blank header defaulting to a "system" tenant is the common form. Duplicate `X-Tenant-Id`, case variants, whitespace, or a proxy-appended header can change which tenant wins; decide explicitly and reject conflicts.
- **`WITH CHECK` absent or policy scoped `FOR SELECT`.** As written the policy defaults to `ALL` and `USING` doubles as `WITH CHECK`, but permissive policies are OR-ed in; one `USING (true)` widens every command.
- **Role drift, null tenants, and restore.** A nullable `tenant_id` is writable by the owner even when invisible to tenants, so make it `NOT NULL` with a foreign key. Recreating the table as the app role or granting `BYPASSRLS` reopens everything, and no test notices while tests use a different role. A restore that omits policies or restores ownership to the app role silently disables isolation.

## Tests required before claiming tenant isolation

Release-blocking tests are marked **RB**.

**Configuration and role identity**
- **T-01 (RB)** In the test connection itself, assert `current_user` is not the table owner, `rolbypassrls = false`, `rolsuper = false`.
- **T-02 (RB)** Assert `relrowsecurity` and `relforcerowsecurity` are true, and `pg_policies` shows `USING` and `WITH CHECK` on all four commands.
- **T-03 (RB)** Refuse to start if the production DSN role is owner or `BYPASSRLS`. T-04: the app role has no direct `INSERT`/`UPDATE`/`DELETE`, only `EXECUTE`.

**Object-level isolation**
- **T-05 (RB)** As the production role, call `update_invoice` with tenant A's context and tenant B's invoice ID: zero rows, row unchanged when read back as owner, no partial write. The same-tenant call updates exactly one row.
- **T-06 (RB)** Payload or arguments attempting to change `tenant_id` are rejected; the row's tenant is unchanged. Cross-tenant and nonexistent IDs return the same status, so the API is not an existence oracle.
- **T-07 (RB, mutation)** Remove the tenant predicate, or grant `BYPASSRLS` to the production role, and confirm T-05 fails. If it still passes, the test is not measuring the guard.

**Tenant context and pooling**
- **T-08 (RB)** Unset `app.tenant_id` errors with no write; empty (T-09) and malformed UUID (T-10) behave the same.
- **T-11** The `current_setting(..., true)` path returns no rows and an explicit error, not an empty success.
- **T-12 (RB)** On a session-pooled connection, a tenant A call followed by a context-free query returns nothing of A's.
- **T-13** Context does not survive `COMMIT`. T-14: interleaved tenants under load never see each other's rows. T-15: repeat through the actual pooler, not only direct Postgres.

**Authentication binding**
- **T-16 (RB)** Authenticated tenant A with `X-Tenant-Id: B` is denied, and the header never reaches SQL. T-17: duplicate conflicting headers are denied.
- **T-18** Missing, expired, or revoked token is denied before any database call. T-19: a tenant A token without the write grant is denied.

**SECURITY DEFINER hygiene**
- **T-20** `prosecdef`, pinned `proconfig` search_path, owner is `NOLOGIN`, non-superuser, non-`BYPASSRLS`. T-21: `EXECUTE` is not granted to `PUBLIC`. T-22: a shadow-object hijack is inert. T-23: the app cannot `ALTER` or `DROP` the function.

**Batch path**
- **T-24 (RB)** A tenant B row in a tenant A batch is rejected before any write, audited, and the job fails visibly.
- **T-25 (RB)** A mixed-tenant file produces no cross-tenant write; choose all-or-nothing or per-row with a report, and assert the choice.
- **T-26** A blank tenant is rejected, never defaulted. T-27: re-running the same batch is idempotent.

**RLS as actual defense in depth**
- **T-28 (RB)** Run the function's SQL as the production non-owner role and confirm RLS filters cross-tenant rows.
- **T-29 (RB)** Disable RLS or drop the policy and confirm the isolation tests fail, proving they exercise RLS rather than role privileges.
- **T-30** After `pg_dump`/restore, rerun T-01, T-02, and T-28.

**Audit and concurrency**
- **T-31** Denied cross-tenant attempts produce an audit row in the same transaction; an audit failure aborts the mutation.
- **T-32** Two concurrent updates with a stale version produce one winner and one conflict, no lost update. T-33: the app cannot `UPDATE` or `DELETE` audit rows.

## Minimum change set

Split the `NOLOGIN` owner from the `LOGIN` app role; make `tenant_id NOT NULL`; enable `FORCE RLS` with explicit `USING` and `WITH CHECK`; revoke direct DML; add `WHERE id = $1 AND tenant_id = $2` plus `ROW_COUNT = 1`; pin `search_path`; derive tenant from verified identity; and give the batch a declared scope. Then run the suite above, including the mutation test.

## Residual risk

`BYPASSRLS`, superuser sessions, and the migration role are privileged, audited operators and out of scope. Pooler behaviour and PostgreSQL version coverage are assumptions until T-15 and T-30 run against deployed versions. Timing side channels and `pg_stat` metadata leakage are not covered. Until T-05, T-07, T-16, T-24, T-28, and T-29 pass against the production role and configuration, the correct description is "RLS is enabled on the table," not "tenant isolation holds."
