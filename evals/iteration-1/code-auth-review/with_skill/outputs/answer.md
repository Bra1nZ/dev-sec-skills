# Tenant Isolation Review — Invoice Update and Batch Import

**Status: BLOCKED. Tenant isolation must not be claimed for this design.**

**Claim under review:** "Only a tenant admin can update an invoice, and no tenant can read or write another tenant's invoices."

**Why the claim fails today:** the only control is a role comparison in one HTTP handler. It is not an enforcement point for the system. The batch import writes through the ORM without any check, the tenant is taken from a client-controlled request body, and the database has no row-level security or tenant constraint. Under the described design:

- A `tenant_admin` of tenant A can update tenant B's invoice by putting tenant B's ID in the request body.
- A `tenant_admin` of tenant A can update tenant B's invoice by targeting its invoice ID if the write is keyed only by invoice ID.
- The batch job can write invoices for any tenant, with no authorization and no audit, because it never enters the handler.
- If the handler's role lookup fails in a permissive way, nothing beneath it denies the write.

The design has a guard on one path, not a property of the system. The invariant map below defines what must hold, where it must be enforced, and what evidence is required before the claim can be made.

---

## 1. Claim decomposition

| Claim | Meaning | Required to be true | Current status |
| --- | --- | --- | --- |
| C1 | Authentication | Every invoice write has a verified principal | Unknown; not stated for batch |
| C2 | Tenant binding | Every write is scoped to exactly one tenant derived from the principal | Violated: tenant comes from request body |
| C3 | Authorization | Principal may update this specific invoice in this tenant | Partial: global role string only; no object check |
| C4 | Path coverage | HTTP, batch, import, admin, scripts, migrations all enforce C1–C3 | Violated: batch bypasses the handler |
| C5 | Fail closed | Missing/unknown/error states deny and leave no write | Unknown; not stated |
| C6 | Defense in depth | Database independently prevents cross-tenant writes | Absent: no RLS |
| C7 | Auditability | Every allowed and denied write is attributable | Unknown; not stated |

A claim of tenant isolation requires all seven. C2, C4, and C6 are already known to fail from the design description alone.

### 1.1 Blocking questions for the author

These change the severity or the fix; answer them with code references before accepting any remediation:

1. Is `tenant_id` ever compared to a server-side value, or is the request body the only source? Where is the comparison, and does it happen before the invoice lookup?
2. Is `role` a global account role, or is it a per-tenant membership? What returns it, and can it be stale after revocation?
3. Is the invoice fetched by ID alone? Does the subsequent write carry a tenant predicate, or does it `save()` the fetched object?
4. What principal and database role does the batch import use? Is its tenant fixed by job configuration or read per row from the file?
5. Is `tenant_id` `NOT NULL` with a foreign key? Are there existing unscoped rows or nullable values?
6. Is there any audit record today? Does it capture denied attempts, or only successful writes?
7. Which other write paths exist outside the handler: admin tools, scripts, bulk endpoints, exports, migrations?
8. Does the update schema allow `tenant_id` or unknown fields through mass assignment?

---

## 2. Invariant map

The "Enforcement point" column is the required single choke point, not a description of the current code. "Failure mode" is what must happen when the invariant is violated or the enforcement itself errors.

| ID | Invariant | Required enforcement point | Failure mode | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| I-01 | Every request-scoped invoice write uses the tenant from the verified principal; request-body tenant is never authoritative | `RequestContext` built only by auth middleware; body `tenant_id` rejected if it differs from the principal's tenant | 400/403 before any DB access; no write | T-01, T-02, T-05 | All HTTP entry points |
| I-02 | An invoice update succeeds only if the principal is authorized for that specific invoice and that invoice's tenant | `InvoiceRepository.update(principal, invoice_id, patch)` issuing `UPDATE invoices SET ... WHERE id = :id AND tenant_id = :principal_tenant RETURNING ...` | 0 rows affected → 404, transaction rolled back | T-03–T-06, T-15 | All update paths |
| I-03 | `tenant_admin` is evaluated for the target tenant and the specific action; role-less, expired, revoked, neighboring-tenant, and platform-admin cases are distinct | Central policy function `authorize(principal, "invoice.update", resource_tenant, invoice)` | Deny with typed 401/403; no write | T-09–T-14 | All actors and tenants |
| I-04 | No code path writes invoices except through the one scoped repository | Repository is the only exported write API; DB grants deny direct table writes to app and batch roles; CI architecture test enumerates every write site | Runtime permission error; CI failure | T-07, T-08, T-36–T-38 | Entire codebase and deployment |
| I-05 | Batch import is an explicit privileged path, permanently bound to one tenant, and applies the same object/tenant rules per row | `ImportPrincipal(tenant_id, job_id, source)` validated from signed/controlled job configuration; same repository as HTTP; per-row tenant mismatch rejects the row or batch | Abort batch by policy; no partial commit; rejection counts reported | T-16–T-20 | Batch, import, backfill |
| I-06 | Missing principal, missing/ambiguous tenant, unknown role, policy error, DB error, or missing RLS context denies the write | Default-deny policy; typed exceptions; no `or True`, no broad `except` around the check; no `assert` for authorization | 401/403/5xx with zero state change | T-10, T-11, T-21, T-22, T-35 | All paths |
| I-07 | Authorization and write are atomic; no check-then-act window | Tenant predicate in the same `UPDATE`/`DELETE`; row lock or serializable isolation where the decision depends on read state | 0 rows affected; no write | T-06, T-14 | Concurrent writers |
| I-08 | The database independently prevents cross-tenant rows from being written or read | `tenant_id NOT NULL`, FK, composite index, RLS enabled with default deny, app connects as a non-owner role, `SET LOCAL app.tenant_id` per transaction | DB error or zero rows; transaction rollback | T-25, T-28–T-31 | Database/platform |
| I-09 | `tenant_id` is immutable after insert; an update patch cannot move a row between tenants | Field allowlist plus DB constraint/trigger or RLS `WITH CHECK` | 400; no write | T-15, T-31 | All writes |
| I-10 | Every allowed and denied write produces an append-only audit record with actor, tenant, invoice, source, and request/job ID | Single audit writer inside the transaction or transactional outbox; app role has no UPDATE/DELETE on audit | Audit failure fails the operation closed (or documented, tested alternative); never silently continues | T-26, T-27 | All writes |
| I-11 | Batch retries and duplicate deliveries are idempotent and cannot overwrite another tenant's row | Unique constraint on `(tenant_id, source_system, source_id)`; upsert includes tenant predicate | Defined conflict handling; no cross-tenant overwrite | T-18 | Batch retries |
| I-12 | Cross-tenant objects are indistinguishable from absent objects; errors leak no tenant IDs, stack traces, or secrets | Central error mapper; consistent 404 policy; no ORM exception text returned | Deny with no state change | T-04, T-33–T-35 | API and batch reporting |
| I-13 | Migrations and backfills preserve tenant scoping and are not an ambient bypass | Migration role, explicit maintenance gate, ordered/restartable migrations, post-migration negative tests | Abort and roll back; gate refuses unset tenant | T-32 | Migrations, recovery |

### Current enforcement versus required

| ID | Current design | Gap severity |
| --- | --- | --- |
| I-01 | Tenant ID taken from request body | Critical |
| I-02 | Role check only; no proof the target invoice belongs to the caller's tenant | Critical |
| I-03 | Single global string comparison `role == 'tenant_admin'`; no tenant binding, no object check, no permission model | Critical |
| I-04 | Batch import uses the ORM directly and never calls the handler | Critical |
| I-05 | Batch has no principal, no tenant binding, no audit described | Critical |
| I-06 | Not described; role check may be bypassed by exception handling or `assert` | High |
| I-07 | Check and write are separate operations in the handler; race and ID-only write possible | High |
| I-08 | No RLS, no stated tenant constraint | Critical |
| I-09 | Not described; mass assignment could allow tenant reassignment | High |
| I-10 | Not described | High |
| I-11 | Not described; import retries may duplicate or cross tenants | Medium |
| I-12 | Not described; ORM "not found" may differ from authorization failure | Medium |
| I-13 | Not described | Medium |

---

## 3. Bypasses

Each item is a path that reaches the protected resource without crossing the intended check, or a way to make the check ineffective.

### B-01 — Batch import bypasses the handler (confirmed)

The import job writes invoices directly through the ORM and does not call `update_invoice`. There is no principal, no role check, no tenant check, and no object-level check. Whatever credential the job uses is the effective authorization. This alone makes C4 false and invalidates the isolation claim.

A guard in the HTTP handler cannot cover this path. Moving the check into a service function that the batch also calls is necessary but not sufficient: the batch still needs an explicit, tenant-bound principal, or it remains an ambient bypass.

### B-02 — Any other direct ORM writer

The handler is not the only way to write. Common bypasses in Python stacks:

- Management commands, cron scripts, one-off repair scripts, notebooks, and REPL sessions.
- Admin console or internal tools that use the ORM or raw SQL.
- Celery/RQ workers and retry tasks.
- Data migration and backfill scripts.
- Reporting/export jobs that write back status fields.
- Tests and fixtures that run against shared environments.

Any of these can update an invoice without the handler. The design must assume they exist and deny them at a lower layer.

### B-03 — Tenant ID from the request body (confirmed)

The body is attacker-controlled. There are two distinct exploits:

1. The handler checks only the role, then writes using `body.tenant_id`. A tenant A admin sets `tenant_id = B` and writes into B.
2. The handler checks the role and uses the body tenant only for the check, but the write is keyed by invoice ID alone. A tenant A admin sends their own tenant in the body, targets B's invoice ID, passes the check, and updates B's row.

The tenant used for authorization and the tenant used in the write predicate must be the same server-derived value. The body may be accepted only as an assertion that must equal the authenticated tenant, never as the source of authority.

### B-04 — Role-only check does not bind the tenant

`current_user.role == 'tenant_admin'` proves only that the principal carries that role string. It does not prove:

- which tenant the role applies to,
- that the principal is a member of the target invoice's tenant,
- that the principal has the specific `invoice.update` permission,
- that the role is current and not revoked.

A tenant A `tenant_admin` is an outsider for tenant B. The design treats them as authorized everywhere the string matches.

### B-05 — Route-level check, not object-level check

Even with a correct tenant check, fetching an invoice by ID and then writing it can cross tenants if the fetch is unscoped. `get_object_or_404(Invoice, id=invoice_id)` followed by `invoice.save()` checks nothing about the row's tenant. The write must carry `WHERE id = :id AND tenant_id = :tenant` and assert that exactly one row was affected.

### B-06 — Bulk and raw operations bypass ORM hooks

If the proposed fix is a model `save()` override, an ORM event, or a signal, these are bypassed by:

- `QuerySet.update()`, `bulk_create()`, `bulk_update()` in Django.
- `session.bulk_save_objects()`, `session.bulk_insert_mappings()`, `session.execute(update(...))` in SQLAlchemy.
- Raw SQL and stored procedures.

A security control must not depend on a hook that bulk paths skip. The enforcement point must be the repository API plus database permissions/RLS.

### B-07 — Read-modify-write in another service or nested call

Another endpoint, internal RPC, GraphQL resolver, or CLI command may fetch an invoice and pass the object to a shared update helper. If the helper trusts the object's current tenant, the authorization decision may have happened in a different context or not at all. The choke point must take the principal and re-derive the tenant; it must not accept a pre-fetched object as proof of authorization.

### B-08 — Database owner or superuser role

If the application or import job connects as the database owner (common in Django/SQLAlchemy setups), RLS is bypassed even when enabled, and table grants do not restrict it. The design already has no RLS, but any future RLS must come with a non-owner runtime role and a separate migration role. Otherwise the "defense in depth" is cosmetic.

### B-09 — Privileged paths without a gate

Migrations, backfills, disaster recovery, support tooling, and maintenance scripts are legitimate bypasses only if they are explicit and gated. An ambient flag (`BYPASS_AUTH=1`, `SYSTEM_USER`, `is_internal=True`) that any request or worker can set is not a gate. Each privileged path needs its own credential, scope, tenant declaration, and audit.

### B-10 — Nullable or defaulted tenant

If `tenant_id` is nullable, absent, empty, or defaulted to `None`/`0`/`"all"`, a missing value can become an unscoped query or a wildcard. A batch row with no tenant must be rejected, not imported into a default tenant. An HTTP request with no tenant must be rejected, not scoped to the caller's tenant silently if the body was supposed to be authoritative.

### B-11 — Tenant reassignment through mass assignment

If the update handler copies body fields onto the model (`setattr` loop) or accepts a partial-update schema without an allowlist, the attacker can include `tenant_id` and move the invoice (and its future access) to a tenant they control. `id`, `created_at`, and ownership fields must be immutable through this endpoint.

### B-12 — Export/import round trip

An export from tenant B can be imported by a tenant A user or job. If the import trusts the file's tenant column, tenant A can create or overwrite rows in B. Import must bind every row to the job's authorized tenant and reject foreign rows, or the import must run as a genuinely privileged, audited cross-tenant operation with its own approval path.

### B-13 — Admin actors treated as implicitly authorized

A platform admin, support engineer, or `is_superuser` flag is not the same as a tenant admin. If the policy has an admin superset branch, it must be explicit, separately gated, audited, and tested. "Admin without the specific grant" is an outsider case that the design must decide and enforce.

---

## 4. Fail-open risks

These are ways the enforcement can error, be skipped, or widen access. Each must be converted into a deny with no state change.

| ID | Risk | Required behavior |
| --- | --- | --- |
| F-01 | `assert current_user.role == 'tenant_admin'` used as the guard. Under `python -O`, asserts are removed and the write proceeds. | Never use `assert` for authorization; use an explicit raise. |
| F-02 | Broad `try/except` around the handler or the policy call catches the authorization exception and continues to the write. | Catch only expected types; re-raise authorization failures; no fallthrough to write. |
| F-03 | `if current_user and current_user.role != 'tenant_admin'` — an anonymous/`None` principal skips the check and is allowed. | Missing principal → 401, explicitly, before any truthiness shortcut. |
| F-04 | `current_user` is a lazy proxy; attribute access fails and the exception handler returns a success-shaped result or retries without the check. | Resolve the principal once at the boundary; on resolution failure deny. |
| F-05 | Role comes from a client header, unsigned token claim, or stale cache; role revocation is not reflected. | Verify the token; read role from the authoritative store or a short-TTL cache with revocation invalidation; test revoked/expired tokens. |
| F-06 | Tenant ID missing from the body defaults to `None`, `0`, `"all"`, or the first tenant found, and the query becomes unscoped. | Missing tenant → 400/403; never a wildcard; DB `NOT NULL`. |
| F-07 | Check-then-act race: handler fetches the invoice, checks tenant, then saves by ID; another writer changes the row between check and save. | Atomic `UPDATE ... WHERE id AND tenant_id`; check affected row count; lock or serializable isolation where needed. |
| F-08 | The write is committed before the check or in a `finally` block; the refusal path leaves a partial write. | Check before any mutation; roll back on refusal; assert DB state in tests. |
| F-09 | Batch per-row `except Exception: continue` swallows authorization failures and commits the remaining rows. | Authorization failure aborts the row or batch per the defined contract; failures are counted and visible, never silently skipped. |
| F-10 | Audit write failure is swallowed so the operation can proceed. | Define and test the policy: fail closed, or an explicit documented exception; never silent. |
| F-11 | A feature flag, environment variable, or `X-Internal` header bypasses the check. | Remove ambient bypasses; privileged paths use separate credentials and gates. |
| F-12 | The policy service or role lookup times out and returns an empty role set; code treats "no roles" as "no restriction" or defaults to allow. | Timeout/error → deny; empty role set → deny; test the timeout path. |
| F-13 | Database error during the write is caught and converted into a 200/empty list, hiding a failed or partially applied operation. | Internal failure → 5xx; no success-shaped empty result. |
| F-14 | The batch job runs with a service account that has `tenant_admin` or superuser, so the same code path "passes" while crossing tenants. | Bind the import principal to one tenant; do not model service accounts as tenant admins. |
| F-15 | Only the handler is tested; a regression adds a new ORM write path and no test notices. | Architecture test enumerating write sites; DB grants/RLS as backstop; mutation test the choke point. |
| F-16 | The role check is computed but not used to gate the write, is performed after the mutation, or only gates the response. | Bind the decision to the write: the repository refuses without an allow decision; test with the check moved after the write and confirm denial. |

---

## 5. Tests required before claiming tenant isolation

The tests below are the minimum evidence. "No write" means assert the row's full state is unchanged, not just that the response is non-2xx. Run them with two seeded tenants (A and B), at least one invoice per tenant, and use the same database role and configuration as production. For RLS tests, run as the non-owner application role, not the owner.

### 5.1 Tenant binding and object authorization

| ID | Setup and action | Expected result | Invariant |
| --- | --- | --- | --- |
| T-01 | Authenticated tenant A `tenant_admin` sends `tenant_id = B` in the body, targeting A's invoice | 400/403; no invoice changed; audit records denial | I-01 |
| T-02 | Same principal omits `tenant_id`; server must derive tenant from the token | Update succeeds only for A's invoice, or the request is rejected per the documented contract; absence never means wildcard | I-01 |
| T-03 | Tenant A `tenant_admin` updates A's invoice | 200; exactly the intended fields changed; one audit row | I-02 |
| T-04 | Tenant A `tenant_admin` targets B's invoice ID with A's tenant | 404 (or documented 403); B's row unchanged; no existence leak | I-02, I-12 |
| T-05 | Tenant A `tenant_admin` sends B's invoice ID and `tenant_id = B` | Denied; no write to B | I-01, I-02 |
| T-06 | Tenant A `tenant_admin` sends B's invoice ID with `tenant_id = A` | 0 rows affected; denied; no write | I-02, I-07 |
| T-07 | A script with no principal calls the repository/ORM directly to update B's invoice | Denied at the repository boundary for lack of a principal; if it bypasses the repository, DB permission/RLS denies it | I-04, I-08 |
| T-08 | Direct bulk update with no principal: `QuerySet.update()` / `session.execute(update(...))` / `bulk_update` against another tenant | Denied by DB grants/RLS or caught by the CI architecture test; not silently allowed | I-04, I-08 |
| T-09 | Tenant A member/viewer (not `tenant_admin`) updates A's invoice | 403; no write | I-03 |
| T-10 | Role-less principal updates any invoice | 401/403; no write | I-03, I-06 |
| T-11 | Expired session or revoked token updates A's invoice | 401; no write | I-03, I-06 |
| T-12 | Platform admin/superuser without the specific tenant grant updates A's invoice | Denied per stated policy; if allowed, explicit gate, audit, and documented scope | I-03 |
| T-13 | Tenant A `tenant_admin` attempts to update an invoice owned by a B user who is also a `tenant_admin` | Denied; role equality is irrelevant across tenants | I-02, I-03 |
| T-14 | Two concurrent requests target the same invoice; one changes tenant/ownership between check and write (or simulate with a pause/lock) | At most one valid write; the stale decision affects 0 rows; no cross-tenant write | I-07 |
| T-15 | Update patch includes `tenant_id`, `id`, `created_at`, or an unknown field | 400; none of the protected fields changed | I-09 |

### 5.2 Batch and import

| ID | Setup and action | Expected result | Invariant |
| --- | --- | --- | --- |
| T-16 | Import job bound to tenant A processes a file containing one B row | B row rejected; no B write; rejection counted; A rows unaffected or batch aborted per contract | I-05 |
| T-17 | Import job has no tenant binding or an empty/`*` tenant | Job fails before any write; no default tenant used | I-05, I-06 |
| T-18 | Import retries the same file twice, including a duplicate `(source_system, source_id)` | Single logical effect per row; no duplicate rows; no cross-tenant overwrite | I-11 |
| T-19 | Import fails halfway through a batch (row 3 of 10 raises) | No partial commit; either full rollback or all rows quarantined with zero writes, exactly as documented | I-05, I-08 |
| T-20 | Batch job's service credential attempts a cross-tenant update outside its bound tenant | Denied at the repository and by DB policy; no write | I-05, I-08 |

### 5.3 Fail-closed and failure injection

| ID | Setup and action | Expected result | Invariant |
| --- | --- | --- | --- |
| T-21 | Force the policy/role lookup to raise a timeout or connection error | 5xx/deny; no write; error does not include a tenant ID or stack trace | I-06, I-12 |
| T-22 | Force the principal resolver to return `None`/anonymous | 401; no write; no `AttributeError` converted into success | I-06 |
| T-23 | Mutation test, policy layer: with the repository and RLS intact, remove the handler's role check and call the API as a non-admin | The request must still be denied somewhere below the handler; the test must record which layer denied. If it is allowed, the handler was the only role control and the policy must move into the repository | Evidence quality |
| T-24 | Mutation test, repository layer: in a test-only configuration with RLS disabled and the policy stubbed to allow, no-op the repository tenant predicate and rerun T-04/T-06/T-15 | They must fail (the cross-tenant write now succeeds), proving the repository predicate is what denied it; restore the predicate and rerun to confirm they pass | Evidence quality |
| T-25 | Mutation test, database layer: as the non-owner application role with `app.tenant_id = A`, query/update B's invoice directly, then disable RLS in the test database and repeat | With RLS on: zero rows/denied. With RLS off: B's rows are visible/updated, so the direct-DB test must fail. This proves the RLS test oracle depends on RLS, not on an empty fixture | Evidence quality |
| T-26 | Audit writer fails during an allowed update | Operation fails and rolls back, or the documented tested alternative; the invoice is not changed silently without a trail | I-10 |
| T-27 | Unauthorized attempt is made, then the audit table is queried | Denial is recorded with actor, tenant, resource, source, and reason; no secret/token in the record | I-10 |
| T-39 | Mutation test, binding: in a test-only build, move the authorization call after the UPDATE or ignore its result | The negative tests must fail (the write now succeeds or the denial is not enforced), proving the decision is actually bound to the write; restore and rerun to confirm they pass | I-06, F-16 |

### 5.4 Database and schema

| ID | Setup and action | Expected result | Invariant |
| --- | --- | --- | --- |
| T-28 | Insert an invoice with `tenant_id = NULL` | Constraint violation; no row | I-08 |
| T-29 | As the application role with no `app.tenant_id` set, query invoices | Zero rows or an explicit error; never all rows | I-08 |
| T-30 | As the application role with `app.tenant_id = A`, select and update | Only A rows visible/updatable; B rows invisible; B update affects 0 rows | I-08 |
| T-31 | Attempt to change an invoice's `tenant_id` via direct SQL under the tenant A context | Constraint/trigger/RLS `WITH CHECK` rejects it | I-08, I-09 |
| T-32 | Run the negative tests after applying all migrations to a copy of live-like data | Same results as on the test schema; no unscoped legacy rows | I-13 |

### 5.5 Error contract and non-enumeration

| ID | Setup and action | Expected result | Invariant |
| --- | --- | --- | --- |
| T-33 | Compare responses for a nonexistent invoice ID and another tenant's invoice ID | Same status and body shape; no tenant ID, owner name, or internal path leaked | I-12 |
| T-34 | Force an ORM/database exception during update | 5xx without SQL, table names, or stack trace; no partial write | I-12, I-06 |
| T-35 | Attempt an update with malformed `tenant_id`, invoice ID, and role headers | Consistent 400/401/403; no 500 that reveals internals; state unchanged | I-12 |

### 5.6 Path inventory (must pass before the claim)

| ID | Check | Expected result | Invariant |
| --- | --- | --- | --- |
| T-36 | Static/CI inventory of every invoice write call site: handlers, services, jobs, commands, migrations, raw SQL, bulk APIs | Every site resolves to the single repository; any exception is an explicit gated privileged path with a test | I-04 |
| T-37 | Enumerate every HTTP route that can reach invoice writes and run the outsider matrix (T-04, T-05, T-09–T-13) against each | No route bypasses the choke point | I-04 |
| T-38 | Grep/architecture test for `role ==`, `is_superuser`, `BYPASS`, `SYSTEM`, `skip_auth`, direct `.save(`, `.update(`, `bulk_` in write paths | No ad hoc policy checks; no ambient bypass flags in the write path | I-04, I-06 |

### 5.7 Minimum gate

Do not claim tenant isolation until all of the following are true:

1. T-01 through T-15 pass against every invoice-write route.
2. T-16 through T-20 pass for the batch/import path.
3. T-21 through T-27 and T-39 pass, including the layer-by-layer mutation tests (T-23–T-25, T-39): each control is removed in a test-only build and the corresponding tests fail, proving they are sensitive to that control.
4. T-28 through T-32 pass with the production database role and all migrations.
5. T-33 through T-35 pass for the error contract.
6. T-36 through T-38 pass the path inventory.
7. The test run records which layer (policy, repository, database) denied each attack; "the API returned 403" alone is not proof that the database would stop a direct ORM write.

---

## 6. Required design changes (blocking)

### 6.1 Replace the handler check with one tenant-scoped write choke point

Create a single repository/service that every write path must call. It takes an authenticated principal and a server-derived tenant, not a body field and not a pre-fetched object.

```python
# Illustrative shape, not a drop-in implementation.
class InvoiceRepository:
    def update_invoice(self, principal, invoice_id, expected_tenant_id, patch):
        if principal is None or principal.tenant_id is None:
            raise Unauthenticated()
        tenant_id = principal.tenant_id
        if expected_tenant_id is not None and expected_tenant_id != tenant_id:
            raise TenantMismatch()
        policy.authorize(principal, "invoice.update", tenant_id, invoice_id)
        fields = allowlist(patch, {"status", "amount", "due_date"})
        rows = self.db.execute(
            update(Invoice)
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .values(**fields)
            .returning(Invoice.id)
        ).all()
        if len(rows) != 1:
            raise InvoiceNotFound()
        audit.record(principal, "invoice.update", tenant_id, invoice_id)
```

Key properties:

- The tenant in the authorization decision and the tenant in the write predicate are the same value.
- The write is atomic with the tenant predicate; a wrong tenant produces 0 rows, not a successful update.
- The patch is an allowlist; `tenant_id` is not mutable.
- The repository is the only exported write API; handlers and the batch both call it.
- The policy function handles role, tenant membership, object-level permission, and outsider cases. If a rule depends on the invoice's current state, load it inside the same transaction under a row lock; do not trust an earlier fetch.
- `audit.record` participates in the same transaction as the write; an audit failure rolls the write back rather than proceeding silently.

### 6.2 Remove the request-body tenant as an authority

Derive the tenant from the verified principal. Treat a body `tenant_id` as an optional assertion: if present, it must equal the principal's tenant and a mismatch is rejected before any lookup or write; if absent, derive the tenant from the principal. If the API contract instead requires the field, reject absence with 400. In neither case may absence mean "all tenants" or a client-chosen default. Never use the body value in the `WHERE` clause.

### 6.3 Make the batch an explicit privileged path

- Give the import job an `ImportPrincipal` bound to exactly one tenant (and job/source identity) from controlled configuration, not from the file's contents.
- Route every imported row through the same repository and policy function as HTTP.
- Reject a row whose tenant differs from the job's tenant; do not silently "fix" it to the job tenant.
- Record the job ID, source file/version, and row count in the audit trail.
- Define batch atomicity: all-or-nothing is simplest to test. If partial success is required, each rejected row must leave zero writes and be reported with a reason.
- Make retries idempotent with a unique `(tenant_id, source_system, source_id)` key.

### 6.4 Add database defense in depth

- `tenant_id NOT NULL` with a foreign key to `tenants`.
- Composite indexes starting with `tenant_id` for all tenant-scoped access paths.
- RLS enabled on `invoices` with `USING` and `WITH CHECK` policies bound to `current_setting('app.tenant_id')`.
- The application and import roles are not table owners and cannot bypass RLS.
- Each transaction sets `app.tenant_id` from the server-derived context; a missing setting yields zero rows, not all rows.
- If the database cannot support RLS, state that explicitly as residual risk and compensate with the repository choke point, restricted grants, an architecture test, and audit. Do not call the result "tenant isolation enforced by the database."

### 6.5 Add audit and error contracts

- One append-only audit writer for allow and deny; no application role UPDATE/DELETE on the audit table.
- Audit fields: actor ID, tenant ID, resource type/ID, action, decision, source (`http`/`batch`/`admin`/`migration`), request/job ID, timestamp, reason code. Never log tokens or full request bodies.
- Consistent error mapping: cross-tenant and absent both return 404 (or both 403 per a documented policy); no ORM text, tenant IDs, or stack traces in responses.
- Authorization failure must roll back; a successful response must mean exactly the intended row changed.

### 6.6 Gate privileged paths

Migrations, backfills, support tooling, and recovery need their own credentials, explicit tenant scope or a documented cross-tenant approval, and audit. No `BYPASS_AUTH`-style ambient flag in request or worker code.

---

## 7. Residual risk and scope statement

Until the changes above are implemented and the tests pass:

- **No tenant isolation claim is supportable.** The HTTP path is vulnerable to body-tenant spoofing and role-only authorization; the batch path has no authorization.
- **No path-coverage claim is supportable.** Only one handler was described; the batch is already a known bypass, and scripts, admin tools, and bulk ORM APIs are unenumerated.
- **No database-enforcement claim is supportable.** RLS is absent; the runtime database role and grants are unspecified.
- **Framework and database are unspecified in the design.** The tests assume a SQL database with row-level security available. If the platform is not PostgreSQL, substitute the equivalent constraint/role mechanism and state which platform was actually tested; do not treat an untested platform as covered.
- **Batch idempotency and audit are undescribed.** They are unproven, not merely untested.
- **Privileged actors and migration behavior are out of scope until gated and tested.** A platform admin, a service account, or a migration that can write any tenant is a deliberate bypass only if it is explicit, credential-separated, and audited.

After the gate in section 5.7 passes, the claim may be narrowed and stated as: "Invoice writes through the HTTP API and the tenant-bound import job are restricted to the authenticated principal's tenant, enforced at the repository and by database RLS, with cross-tenant attempts denied and audited. Tested on `<database/version>` with `<runtime role>`; privileged migration and support paths are documented separately." Anything broader is not supported by the evidence.
