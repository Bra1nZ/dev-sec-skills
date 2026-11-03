# Tenant Isolation Review: Invoice Update and Batch Import

**Verdict: tenant isolation is not established.** A role check in one HTTP handler is not a tenant authorization boundary. The design has at least three independent isolation failures:

1. The tenant is taken from the request body, which is attacker-controlled.
2. The handler is not required to authorize the specific invoice against the caller's tenant.
3. The batch import bypasses the only stated authorization check.

The absence of row-level security (RLS) removes the database backstop, so any missed application predicate becomes a full cross-tenant exposure.

*Basis: design description only; no source code was inspected. This is a threat-model and test-plan review.*

---

## 1. Invariant map

For every committed invoice insert or update `w`, performed by principal `p` on invoice `i`, the following must hold:

- `p` is authenticated, active, and attributable to a human or workload identity.
- `p` has an explicit set of permitted tenants, `T(p)`, derived from trusted identity or job configuration.
- The new tenant of `i` is in `T(p)`.
- For updates, the old and new tenant of `i` are identical, and the old tenant is in `T(p)`.
- `p` has the specific permission (for example, `invoice:update`) in the scope of the target tenant.
- The update is conditioned on both the invoice identity and the target tenant in the same write operation.
- The same rules apply on every write path, including HTTP, batch, CLI, jobs, webhooks, admin tooling, and raw SQL.
- Missing, malformed, ambiguous, or conflicting tenant context denies the write.

For a batch job specifically: `T(job)` must be an explicit, non-empty allowlist. Every row's tenant must belong to `T(job)`. An empty or missing allowlist must deny, never mean "all tenants." A cross-tenant batch mode, if it exists, must be a separate privileged operation with strong authorization and audit.

| ID | Invariant | Current design | Assessment |
|---|---|---|---|
| I1 | Every write has an authenticated, active principal and an attributable authorization context. | HTTP authentication is implied; the batch job's identity and authorization are unspecified. | Partial / not shown |
| I2 | Tenant identity is derived from trusted principal or job grants; request body is only an untrusted claim. | Tenant ID comes from the request body. | **Violated** |
| I3 | Role or permission is evaluated per tenant, for the specific action and resource type. | Only `current_user.role == 'tenant_admin'` in one handler; no stated target-tenant membership check. | Partial / **violated** |
| I4 | The specific invoice belongs to an allowed tenant; role alone is not object authorization. | No stated object-level or tenant-scoped lookup. | Not shown |
| I5 | `tenant_id` and ownership are immutable on update; inserts cannot set them outside grants; upserts cannot reparent. | No stated field allowlist, immutability rule, or upsert key policy. | Not shown |
| I6 | All mutation paths enforce the same policy at a shared boundary. | Handler enforces; batch writes directly through the ORM and does not call it. | **Violated** |
| I7 | Batch jobs use an explicit tenant allowlist; each row is validated; empty or missing allowlist denies. | No stated batch scoping. | Not shown / likely **violated** |
| I8 | Missing, null, empty, malformed, conflicting, or ambiguous tenant context fails closed. | Body source plus unspecified defaults and parsing; fail-closed behavior is not established. | Not shown |
| I9 | Authorization and write are atomic; the update predicate includes invoice ID and tenant ID (and a version where needed). | No stated atomic tenant-scoped update; a fetch-then-write pattern is possible. | Not shown |
| I10 | Database enforces tenant integrity and provides defense in depth. | RLS is explicitly absent; `tenant_id` nullability, foreign keys, and composite keys are unspecified. | **RLS violated**; constraints unknown |
| I11 | Writes and denials are auditable with trusted actor, tenant, target, action, and outcome. | Not stated. | Not shown |

---

## 2. Bypasses

### B1. Request-body tenant spoofing (Critical)

A tenant administrator of tenant A can send `tenant_id=B` in the update payload. The role check passes because the caller is an administrator somewhere; the write then targets tenant B.

This is the most direct HTTP bypass. It is also a trust-boundary defect: the handler should never treat the request body as the source of the caller's tenant. Even if the handler compares the body tenant to `current_user.tenant_id` before writing, the body should not be the value that drives the write, and other paths still need the same check.

**Impact:** cross-tenant create, update, or disclosure; data corruption; an administrator of one tenant acting as an administrator of another.

**Required fix:** derive the tenant exclusively from the authenticated principal or the job's trusted configuration. If the API accepts a tenant identifier in the body, reject it unless it equals the trusted tenant, and never use it before that validation. Prefer removing tenant from the mutable request schema.

### B2. Invoice-ID IDOR / target not scoped (Critical)

The role check says nothing about the invoice being updated. If the handler fetches or updates by `invoice.id` alone, an administrator of tenant A can update tenant B's invoice by supplying B's ID. This remains a bypass even when the body tenant is A, or when the body tenant is validated against the caller.

This can occur through either:

- `SELECT * FROM invoices WHERE id = ?` followed by an update, or
- `UPDATE invoices SET ... WHERE id = ?` without a tenant predicate.

**Impact:** cross-tenant modification of arbitrary invoices by any tenant administrator.

**Required fix:** scope both the read and the write by tenant, and make the update conditional on `(invoice_id, tenant_id)`. Return a uniform not-found response when the scoped row does not exist.

### B3. Mass assignment and tenant reassignment (Critical)

If the update payload is passed to the ORM without an allowlist, a caller may change `tenant_id`, `owner_id`, `customer_id`, or nested relationships. That can move an invoice into another tenant, attach it to another tenant's customer, or alter authorization-relevant ownership.

`session.merge()`, `INSERT ... ON CONFLICT`, and `update_or_create` patterns can produce the same result when the client controls the primary key or a globally unique external identifier.

**Impact:** ownership takeover, cross-tenant reparenting, or overwriting a foreign invoice.

**Required fix:** explicit update DTO and field allowlist. Treat `id`, `tenant_id`, ownership, and all relationship foreign keys as immutable unless changed through a separately authorized operation. Validate that related entities belong to the same tenant.

### B4. Batch import bypass (Critical)

The batch import writes invoices directly through the ORM and never invokes the handler's role check. It is therefore outside the only stated authorization control.

If the import file, queue message, object-storage path, job parameter, or tenant mapping can contain a tenant identifier, a malicious or malformed row can write into any tenant. If the job runs with a broad database credential, the database will not stop it because there is no RLS.

Even if the batch job is considered trusted, this is still a bypass of the stated application control: a compromised import source, a configuration mistake, or an operator error can corrupt or disclose another tenant's data.

**Impact:** bulk cross-tenant insert, update, or overwrite; high-volume data corruption; possible cross-tenant disclosure through import results or logs.

**Required fix:** give the job a workload identity with an explicit allowed-tenant set. Enforce the same repository/service policy used by HTTP. Validate each row and the entire file against that set. Default deny when the set is absent or empty. Provide a separately authorized, audited break-glass mode only if genuinely required.

### B5. Batch upsert / identifier collision (High)

If invoice primary keys, invoice numbers, or external IDs are unique globally rather than per tenant, an import for tenant A can collide with a tenant B record. A merge or upsert can then overwrite B's invoice or change its tenant.

**Impact:** silent cross-tenant overwrite, especially during repeated imports.

**Required fix:** use tenant-aware composite identity for external keys and conflict handling; never let an untrusted file supply the database primary key; check the existing row's tenant before any update.

### B6. Other non-HTTP write paths (High)

The same gap that affects the batch job applies to every other direct writer: management commands, migration and backfill scripts, support tools, ETL pipelines, asynchronous workers, retry jobs, webhook processors, and test fixtures. Any of them can write an invoice without the handler's check.

**Required fix:** centralize writes behind a policy-enforcing repository or service. A direct ORM write to invoices should be either impossible by construction or restricted to a small, reviewed set of system operations.

### B7. Alternate HTTP surfaces and bulk operations (High)

The check exists in one handler. A bulk update endpoint, alternate HTTP method, versioned route, GraphQL mutation, internal RPC endpoint, or a newly added handler may reuse the ORM and omit the check. Bulk operations are especially risky because one foreign ID in a list can expose or modify multiple rows.

**Required fix:** enforce authorization in the shared data-access layer, not in individual route handlers. Add route-level tests for every mutation surface.

### B8. Child and nested resources (High)

Invoice lines, attachments, payments, notes, and customer relationships may be addressable by their own IDs. If a child is fetched or updated by child ID without checking its parent invoice and tenant, the caller can modify another tenant's data. Cross-tenant foreign keys can also attach an invoice to the wrong tenant's customer.

**Required fix:** carry `tenant_id` on tenant-owned child tables or use composite foreign keys; scope every child operation through a tenant-scoped parent; enforce same-tenant relationships at the database where possible.

### B9. Check-then-write race / TOCTOU (Medium to High)

If the code loads an invoice, checks that it belongs to the caller, and then performs a separate update by ID, the authorization decision and the mutation are not atomic. A concurrent operation or a reparenting bug can change the row between the two statements. The update may then affect a row that was not the one authorized.

**Required fix:** perform a single atomic update with `id`, `tenant_id`, and an optimistic version or equivalent condition; require exactly one affected row; otherwise deny.

### B10. No database-level boundary (High, defense-in-depth gap)

With no RLS, a missed `WHERE tenant_id = ...`, SQL injection, an overprivileged batch credential, a support query, or a compromised application process has unrestricted access to all tenants.

**Impact:** any application-layer mistake becomes a full tenant breach rather than a contained incident.

**Required fix:** add RLS or equivalent database policy as a second layer, applied to all tenant-owned tables and child tables. Use a non-owner application role that cannot bypass RLS. Keep application-level enforcement because RLS does not replace the authorization model.

### B11. Role semantics are not tenant-scoped (High)

The string `tenant_admin` does not identify which tenant the administrator belongs to. If the role is global, or if the code never checks the caller's membership in the target invoice's tenant, then an administrator of A is effectively an administrator of B for this operation.

**Required fix:** model roles and permissions as per-tenant grants. Authorize `(principal, action, resource, target_tenant)`, not just the role name.

---

## 3. Fail-open risks

The design does not specify how these cases are handled. Each should be checked in the implementation and covered by a test. Any "allow" path here breaks tenant isolation.

| ID | Fail-open pattern | Why it is dangerous | Required behavior |
|---|---|---|---|
| F1 | Missing tenant becomes `None`, `"*"`, the first tenant, or a default tenant. | An omitted field can select all tenants or an unintended tenant. | Missing tenant denies. Never infer a default for a write. |
| F2 | Tenant filter is applied conditionally, such as `if tenant_id: query.filter(...)`. | `None`, `""`, `0`, or an empty list skips the filter, returning or updating all tenants. | Tenant is mandatory and validated before the query is built. |
| F3 | Batch allows an empty or missing tenant allowlist to mean "all tenants." | A configuration omission becomes a global import. | Empty or missing allowlist denies. "All" requires a separate explicit privilege. |
| F4 | A service, system, or batch role bypasses the authorization check entirely. | Any caller or job that reaches that identity gets unrestricted access. | No blanket bypass. System operations use explicit tenant grants and are audited. |
| F5 | Authorization exceptions, missing user objects, or `None` decisions are treated as allowed. | An outage or malformed token becomes an authorization bypass. | Exceptions and missing decisions deny. The request fails without writing. |
| F6 | Code fetches by ID without a tenant filter, then checks tenant only if the row is found, or falls back to an unscoped fetch when the scoped fetch fails. | A missing row or a logic branch can silently widen the search. | A scoped miss denies. There is no unscoped retry. |
| F7 | Conflicting tenant values are accepted from JSON, query parameters, headers, or duplicate keys, and different layers resolve them differently. | An attacker can make the authorization layer see tenant A while the write uses tenant B. | One canonical parser; reject duplicates, arrays, conflicting sources, and type coercion. |
| F8 | `tenant_id` is nullable or orphaned rows are accepted. | A null-tenant row may match `tenant_id IS NULL`, be treated as global, or be updated by fallback logic. | `tenant_id` is `NOT NULL`; orphan data is quarantined and migrated. |
| F9 | ORM bulk update, merge, or upsert bypasses model hooks, validators, or policy checks. | A bulk path can write rows that the normal save path would reject. | All bulk writes use the same policy-enforcing repository and tenant predicate. |
| F10 | Role, membership, or tenant claim is cached or embedded in a long-lived token and is not rechecked after revocation or reassignment. | A removed administrator can continue writing for the token or cache lifetime. | Define and test a revocation/TTL policy; sensitive writes recheck current membership. |
| F11 | The write commits before authorization completes, or a later failure is ignored after the commit. | The response may look like a denial while the row was already changed. | Authorize and write in one transaction; roll back on failure; assert database state in tests. |
| F12 | No RLS or equivalent database policy. | Every missing application filter is immediately a cross-tenant breach. | Add defense-in-depth database enforcement and least-privilege roles. |

---

## 4. Tests required before claiming tenant isolation

The test contract is: for every committed write, the stored invoice's tenant must belong to the principal's trusted tenant set, except for an explicitly authorized and audited break-glass operation. A `403` response is not sufficient evidence; each test must also inspect the database state after the request.

Use at least two tenants, A and B, with:

- `adminA`: `tenant_admin` in A only.
- `memberA`: non-administrator in A.
- `adminB`: `tenant_admin` in B.
- `batchA`: workload identity allowed to write only tenant A.
- Invoices `invA`, `invA2`, and `invB`, plus child records and a shared external identifier that exists in both tenants.

### 4.1 HTTP and API tests

| ID | Invariants | Test | Required result |
|---|---|---|---|
| H1 | I1, I3, I4 | `adminA` updates `invA` with the tenant omitted from the body. | Success; only `invA` changes; its tenant remains A. Positive control. |
| H2 | I2, I4 | `adminA` updates `invB` while sending `tenant_id=B`. | Deny (403 or uniform 404); `invB` is unchanged. This is the body-spoofing test. |
| H3 | I2, I4 | `adminA` updates `invB` while sending `tenant_id=A`. | Deny; `invB` is unchanged. A valid body tenant must not authorize a foreign target. |
| H4 | I8 | Omit the tenant; send `null`, `""`, `0`, `"*"`, an array, an unknown tenant, mixed case, or duplicate/conflicting tenant values in JSON, query, and headers. | Every case denies with no write. No default, wildcard, or fallback is used. |
| H5 | I5 | Send `tenant_id=B`, `id`, `owner_id`, or nested relationship changes in an update to `invA`; also attempt to create an invoice with tenant B. | Immutable fields are rejected or ignored; `invA` remains in A; no B row is created. |
| H6 | I1, I3 | Exercise `memberA`, an unauthenticated caller, `adminB` against `invA`, a suspended user, a suspended tenant, and a user with multiple roles/memberships. | All unauthorized cases deny; only a valid administrator of the target tenant succeeds. |
| H7 | I4 | Enumerate sequential IDs or guessed UUIDs for tenant B invoices and attempt reads/updates. | No cross-tenant data is returned or changed; responses do not reveal whether a foreign object exists. |
| H8 | I6 | Exercise PUT, PATCH, any bulk endpoint, GraphQL mutation, internal RPC, and versioned routes. For bulk, mix A and B IDs. | Same policy on every route. A bulk request containing a foreign ID is rejected atomically or rejects that row, with no B write. |
| H9 | I4, I10 | Update a child row belonging to `invB`; attach an A invoice to a B customer; move a child between tenants. | Deny; parent and child remain in the same tenant; no cross-tenant relationship is created. |
| H10 | I9 | Race two updates against the same invoice, including one attempt to change tenant or ownership, using separate connections. | Final state is consistent; an update based only on a stale pre-check cannot commit; the tenant-scoped update affects exactly the expected row. |
| H11 | I1, I3, F10 | Remove the user's administrator role or tenant membership, then reuse an existing session/token or cached authorization decision. | The write is denied within the documented revocation window; no tenant write succeeds under stale authority. |

### 4.2 Batch and other non-HTTP write tests

| ID | Invariants | Test | Required result |
|---|---|---|---|
| J1 | I1, I7 | `batchA` imports valid tenant A invoices. | Success; every inserted or updated row remains in A. Positive control. |
| J2 | I2, I7 | `batchA` imports a row with tenant B, both as an insert and as an update to an existing B invoice. | Deny the row or abort the import according to a defined transaction policy; zero B rows are written or changed. |
| J3 | I7, I8 | Omit the tenant on a row; use `null`, `""`, `"*"`, an unknown tenant, an empty job allowlist, or a missing job configuration. | Every case denies; no default or global mode. An empty allowlist must not mean all tenants. |
| J4 | I5, I7 | Import a file containing the primary key or external ID of `invB` while scoped to A; include one external ID shared by A and B. | `invB` is unchanged; identity and uniqueness checks are tenant-aware; no merge or upsert can overwrite across tenants. |
| J5 | I1, I6 | Forge or change the tenant in the import file, queue message, object-storage path, or job parameter; invoke the job through an unauthenticated or unauthorized trigger. | The allowlist cannot be expanded by untrusted input; the trigger is authenticated and authorized; the job cannot select an arbitrary tenant. |
| J6 | I8, I9 | Make one row invalid after other rows have been processed; retry the same import; simulate a worker crash mid-import. | The documented atomicity policy holds, no cross-tenant writes occur, and retries are idempotent without tenant drift or duplicates. |
| J7 | I7 | Give the job an allowlist of A and B; include rows from A, B, and C. | A and B rows follow policy; C rows are rejected; no row outside the allowlist is written. A wildcard mode, if any, requires a separate explicit privilege and audit. |
| J8 | I6 | Call the CLI, admin script, webhook handler, async retry, and repository directly without a principal or tenant context; also attempt a direct ORM write. | No write occurs; the shared repository requires trusted context. Any approved direct-write exceptions are enumerated, reviewed, and tested. |

### 4.3 Database and static enforcement tests

| ID | Invariants | Test | Required result |
|---|---|---|---|
| D1 | I10 | Inspect and exercise schema constraints: `tenant_id NOT NULL`, tenant foreign key, composite parent-child foreign keys, and tenant-aware unique keys. | Invalid or cross-tenant inserts/relationships fail at the database; orphan and null-tenant rows cannot be created through normal paths. |
| D2 | I10 | With a non-owner application role, set the database tenant context to A and attempt to select, update, and delete B rows, including child tables. Repeat for `batchA`. | Zero B rows are visible or mutable. The role must not have `BYPASSRLS`. If RLS is not implemented, record this as an unmitigated gap; application tests alone do not provide this guarantee. |
| D3 | I6, I9 | Review all invoice write code and assert through SQL logging or a repository contract that every update/delete includes a tenant predicate and every insert has a trusted tenant. | No unscoped invoice write exists outside the approved policy layer. This is an audit/static gate, not proof of runtime correctness. |
| D4 | I9 | Inspect the generated update or call the repository with a mismatched ID/tenant pair. | The update affects zero rows and is treated as not found/denied; the code does not issue a second unscoped update. |
| D5 | I8 | Test existing rows with null, unknown, or inconsistent tenant values; run the migration/backfill and retry normal reads and writes. | Legacy bad rows are not exposed or updated through normal tenant paths; the cleanup is verified and auditable. |

### 4.4 Cross-cutting tests

| ID | Invariants | Test | Required result |
|---|---|---|---|
| X1 | I1–I10 | Property-based or model-based test: generate random principals, tenant grants, invoice IDs, body tenants, payload fields, and operation sequences across every write API. | No committed row ever acquires a tenant outside the principal's grant; no cross-tenant read or write succeeds; denied operations leave the database unchanged. |
| X2 | I8 | Inject authorization-backend failures, database errors, timeouts, missing configuration, and malformed tenant context. | Every failure path denies and commits nothing. No exception handler converts an error into an allow. |
| X3 | I11 | Perform allowed and denied cross-tenant writes and inspect audit records. | Each record contains trusted actor identity, tenant, target, action, outcome, and request/correlation ID; the body-supplied tenant cannot forge the audit tenant; cross-tenant attempts are alertable. |
| X4 | I2, I8 | Fuzz tenant parsing with duplicate keys, Unicode, whitespace, type confusion, arrays, overlong values, and conflicting JSON/form values. | One canonical parse; ambiguous input is rejected; the value used for authorization is the same one used for the write. |

---

## 5. Minimum exit criteria

Do not claim tenant isolation until all of the following are true:

- Every invoice write path is inventoried: HTTP handlers, batch, CLI, jobs, webhooks, admin tools, migrations, and direct ORM usage.
- No write uses a request-body tenant as authority. The tenant comes from a trusted principal or an explicit workload grant.
- Every update is atomically scoped by invoice ID and tenant; a mismatch affects zero rows and is denied.
- `tenant_id` and ownership are immutable through normal update and import paths.
- The batch job has a non-empty, explicit tenant allowlist, and empty or missing configuration denies.
- Cross-tenant tests H2, H3, H4, H5, H8, J2, J3, J4, J5, D1, and X1 pass with database-state assertions.
- RLS or an equivalent database policy is implemented and tested with a non-bypassing application role, or the residual defense-in-depth gap is explicitly accepted and documented.
- All write paths share the same policy-enforcing repository/service rather than relying on per-handler checks.

The current design fails the core invariant: a tenant administrator is authorized somewhere, but not necessarily for the invoice or tenant being written. The batch job does not even pass through that incomplete check.
