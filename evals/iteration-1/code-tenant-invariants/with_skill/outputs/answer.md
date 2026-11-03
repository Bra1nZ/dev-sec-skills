# Invariant Design — Multi-Tenant Invoice API

**Status:** design-ready. This document defines the invariants, enforcement points, failure modes, and negative tests for the invoice create/update service. It is written to be implemented and reviewed, not summarized.

**Reference platform:** PostgreSQL 15/16 as the system of record; one primary writer. The design relies on row-level security (RLS), composite foreign keys, row locks, `SECURITY DEFINER` functions with pinned `search_path`, and transaction-local settings. A deployment on a database without equivalent constraints must re-derive the enforcement points, not copy the application checks.

**Configuration values used throughout:**

| Setting | Value | Why |
| --- | --- | --- |
| `idempotency_retention` | 30 days | Response replay window; the invoice creation key itself is permanent. |
| `max_client_retry_window` | 7 days | Clients must retry within this window; retention must be at least this value. |
| `lease_ttl` | 60 s | Worker lease lifetime. |
| `lease_renew_interval` | 20 s | Renew well before expiry. |
| `worker_commit_timeout` | 30 s | Must be strictly less than the remaining lease. |
| `keyring_refresh_interval` | 15 s | Poll/watch interval. |
| `keyring_rotation_slo` | 60 s | New key must be effective on every replica within this time. |
| `keyring_overlap` | 15 min | Old key acceptance window before `retire_at`. |
| `keyring_max_staleness` | 5 min | After this without a successful refresh, fail closed. |
| `db_clock` | `clock_timestamp()` | Leases, grant windows, and audit times use database time, not application host time. |

---

## 1. Scope and trust model

### 1.1 Actors

| Actor | Description | Authority |
| --- | --- | --- |
| `user` | Authenticated member of exactly one tenant. | Only actions granted by their tenant membership. |
| `admin` | Platform administrator. Has no implicit access to any tenant. | Only an explicit, active `admin_grants` row for the target tenant **and** action, presented as a grant id and revalidated by the server. |
| `worker` | Internal job runner. | Only writes through `commit_worker_write()` while holding the current lease for that invoice. |
| `operator` | Break-glass database operator. | Out of scope for this API. Must use a separately gated, audited path. |
| `anonymous` / `role-less` / `expired` | No valid principal or no effective membership. | Denied everywhere. |

The platform `admin` role is not a tenant membership and is never a substitute for one. If an admin is also a member of a tenant, actions on the normal user surface are member actions under I-03; actions on the admin surface always require I-04's grant.

### 1.2 Entry points that must be covered

Every path below is in scope. A new path is not "covered" until it is added to the architecture test in T-17 and passes the tenant tests.

| Entry point | Reads invoices | Writes invoices | Required choke point |
| --- | --- | --- | --- |
| REST `GET /v1/invoices`, `GET /v1/invoices/{id}` | yes | no | `authorize_invoice_action` + `InvoiceRepository` |
| REST `POST /v1/invoices` | yes | yes | `authorize_invoice_action` + create transaction |
| REST `PATCH/PUT /v1/invoices/{id}` | yes | yes | `authorize_invoice_action` + versioned update |
| REST `DELETE /v1/invoices/{id}` (if enabled) | yes | yes | Same; deletion must retain the creation-key tombstone |
| Search / export / report endpoints | yes | no | Same tenant scope; no unfiltered SQL |
| Batch create / import | yes | yes | One tenant per request; preflight all items; one transaction |
| Admin `GET /admin/tenants/{tenant}/invoices...` | yes | no | `authorize_admin_action` + tenant scope |
| Admin `POST/PATCH /admin/tenants/{tenant}/invoices...` | yes | yes | `authorize_admin_action` + versioned update |
| Worker job / lease commit | yes | yes | `commit_worker_write` + lease fence |
| Outbox consumer | yes | sometimes | `processed_worker_events` + same repository/commit path |
| CLI maintenance / backfill | yes | yes | Gated maintenance job with explicit tenant scope; no ambient raw SQL |
| Migration / restore | yes | yes | Separate migration role; not a runtime API path |

### 1.3 Trust boundaries

- The API gateway may terminate TLS and validate tokens, but the service revalidates authentication and always performs its own authorization. The gateway is defense in depth, never the only guard.
- The application connects to the database as a role that is not the table owner and does not have `BYPASSRLS`. RLS is a second guard behind the application authorization check.
- `admin_grants` is readable only through the grant-check function; the application role has no direct `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on it.
- `audit_events` is writable only through the shared audit append path. Runtime roles cannot update or delete audit rows.
- Worker roles have `EXECUTE` on the worker commit function but no direct `UPDATE` on invoice tables.
- Secrets come from the deployment secret store. Environment variables, source files, fixtures, and build artifacts are not secret sources.

### 1.4 Explicitly out of scope

- Grant issuance UI/service and approval workflow. This API only consumes grants. The grant service must be separately authorized and audited; the database check `created_by <> admin_user_id` blocks self-grants even if that service is compromised.
- Tenant deletion, tenant merge, and invoice hard deletion. If invoice deletion is added, the `(tenant_id, creation_idempotency_key)` tombstone must remain so a late retry cannot recreate a duplicate.
- Tax calculation and monetary rounding rules. I-18 only asserts that stored totals agree with the server's computed result.
- Cross-region active-active writing. This design assumes one primary writer and database-serialized contention.
- Direct operator break-glass access. It must bypass neither audit nor the documented emergency procedure.
- Database credential rotation by the platform connection pooler. If that rotation does not meet the same no-restart and stale-credential rules, I-14..I-17 are not satisfied for that secret class.

---

## 2. Design rules

1. **One tenant per request.** No endpoint accepts a cross-tenant batch. Admin multi-tenant work is one request per tenant, each with its own grant.
2. **One authorization choke point.** User and admin handlers call `authorize_invoice_action()` or `authorize_admin_action()`; both return an opaque `TenantScope`. Repositories and commit functions accept only that scope, never a raw `tenant_id` from the request.
3. **One mutation transaction.** Invoice, line items, idempotency record, audit event, and outbox event commit together or not at all. No external side effect happens before commit.
4. **Database constraints for concurrency.** Unique keys, version predicates, lease primary keys, and fencing-token checks are enforced in the database, not only in application code.
5. **Fail closed.** An error, timeout, missing configuration, unknown action, unavailable policy store, or stale keyring denies or aborts. There is no allow-on-error path.
6. **Denial is not silently successful.** Internal failure never becomes `200` with an empty list or an empty result. The error contract in section 6.9 is part of the invariant.
7. **Explicit privileged paths.** Admin, maintenance, migration, and break-glass paths are named, gated, and audited. There is no ambient `BYPASS_AUTH` or "internal" flag.

---

## 3. Requirement-to-invariant coverage

| Requirement | Invariants | Primary negative tests |
| --- | --- | --- |
| A user can touch only their tenant's invoices. | I-01, I-02, I-03, I-05 | T-01..T-10, T-17 |
| Admins can act only with an explicit grant. | I-04 (with I-03 and I-05) | T-11..T-16 |
| Retries must not create duplicate invoices. | I-06, I-07, I-08 (updates) | T-18..T-27 |
| A worker that lost its lease must not commit. | I-11, I-12, I-13 | T-32..T-37 |
| Secrets rotate without a restart. | I-14, I-15, I-16, I-17 | T-38..T-42 |

---

## 4. Invariant map

| ID | Invariant | Enforcement point | Failure mode | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| I-01 | No invoice or invoice child row is read or written outside the effective tenant. | `authorize_*` returns `TenantScope`; `InvoiceRepository`; PostgreSQL RLS on every tenant table. | Deny: 404 for cross-tenant objects, empty scoped lists; write transaction aborts. | T-01..T-06, T-10, T-17 | All reads/writes, all entry points |
| I-02 | An invoice's tenant is immutable, and every child/reference row resolves to an invoice in the same tenant. | Composite FKs `(tenant_id, invoice_id)`; `UNIQUE (tenant_id, id)`; immutable-tenant trigger; column privileges. | Abort: constraint/trigger error; no change. | T-07 | Invoice, lines, attachments, events, leases, idempotency |
| I-03 | An invoice action is allowed only for an authenticated principal with an active tenant membership and the specific action permission. | `authenticate()` + `authorize_invoice_action()`; closed action enum. | Deny: 401 for unauthenticated/expired; 403 for missing permission; no state change. | T-08, T-09, T-45 | All user entry points |
| I-04 | Every admin invoice action requires an explicit, active, unrevoked, unexpired grant for that admin, tenant, and action; the admin role alone never authorizes. | `authorize_admin_action()` `SECURITY DEFINER`; `FOR SHARE` on `admin_grants`; grant id header. | Deny: 403 `ADMIN_GRANT_REQUIRED`; 503 on grant-store failure; no state change. | T-11..T-16 | Admin surface and any admin-authority path |
| I-05 | Every path that can touch invoice data uses the same authorization and data-access choke points; no ambient flag or lower-level API bypasses them. | Typed `TenantScope`; repository-only SQL; separate DB roles; architecture/static test; startup config validation. | Startup fails on a known bypass configuration; unknown path denied; no writes. | T-17, T-04, T-36 | HTTP, batch, import, admin, worker, CLI, outbox, migration |
| I-06 | At most one invoice exists for a given `(tenant_id, creation_idempotency_key)` for the lifetime of the invoice; a valid retry returns the original invoice. | `UNIQUE (tenant_id, creation_idempotency_key)` on `invoices`; idempotency transaction; response replay. | Replay original result; conflicting retry gets 409; no second invoice. | T-18, T-19, T-23..T-25 | Create, batch create, import |
| I-07 | Reusing an idempotency key with a different principal, operation, or canonical payload is rejected without creating or mutating an invoice; tenant-scoped keys never resolve across tenants. | Request hash + principal + operation stored with the key; comparison after unique conflict. | 409 `IDEMPOTENCY_KEY_REUSED`; rollback; no state change. | T-20..T-22 | All mutating endpoints |
| I-08 | An update commits only for the version the client observed; at most one concurrent update per version commits; a replay with the same key does not apply twice. | `UPDATE ... WHERE version = :expected`; row lock; idempotency record. | 409 `VERSION_CONFLICT`; no write; replay returns original response. | T-26, T-27 | Updates and batch updates |
| I-09 | A mutation commits invoice + lines + audit + outbox together or none of them; every refusal/failure leaves no partial business state and no success-shaped result. | One database transaction per mutation; audit/outbox inserts in that transaction; outbox dispatcher after commit. | Rollback and 4xx/5xx; no invoice, line, success audit, or outbox row. | T-28..T-30, T-45 | Create, update, batch, worker |
| I-10 | Every committed invoice mutation has an append-only audit event with actor, tenant, action, invoice id, request id, decision, and resulting version; runtime roles cannot alter the trail. | Single `audit_append()` channel; insert-only grants; trigger rejecting update/delete; optional hash chain. | Mutation aborts if its audit event cannot be written; denial remains a denial if denial audit fails. | T-29, T-31 | All invoice mutations and admin decisions |
| I-11 | At most one active lease exists per invoice; a takeover after expiry increments a strictly monotonic fencing token. | `invoice_leases` primary key; atomic upsert with `WHERE expires_at <= clock_timestamp()`; `fencing_token + 1`. | Acquire fails with 409 `LEASE_BUSY`; no lease created. | T-32 | Worker lease acquisition |
| I-12 | A worker commit is accepted only with the current, unexpired lease token for the same holder and tenant; a stale or expired worker cannot commit. | `commit_worker_write()` checks holder, token, tenant, and expiry under a row lock in the same transaction as the write; worker has no direct table `UPDATE`. | 409 `LEASE_LOST`; full rollback; no invoice/audit/outbox change. | T-33..T-36 | All worker writes |
| I-13 | A worker side effect is applied at most once per `(tenant_id, invoice_id, operation, source_event_id)`. | `processed_worker_events` primary key inserted in the same transaction as the effect. | Duplicate delivery returns the prior result/no-op; no second effect. | T-37 | Jobs, outbox consumers |
| I-14 | A newly published secret version becomes effective for new signatures/credentials within 60 s without a process restart on every replica. | `SecretProvider` watch/poll; atomic keyring swap; per-request snapshot; no boot-only cache. | Refresh failure keeps last known good only until I-16's staleness bound. | T-38 | Signing keys, tenant API keys, webhook secrets |
| I-15 | After a secret's `retire_at`, it is rejected; before it, it may be accepted only in the configured overlap; there is no indefinite old-key acceptance. | Keyring `not_before`/`retire_at` checks; tenant API-key record `retire_at`/`revoked_at`; rotation procedure sets the deadline. | 401 `CREDENTIAL_EXPIRED` or signature verification failure; no fallback. | T-39 | All rotating secrets |
| I-16 | If the secret store is unavailable or returns an invalid keyring, the service keeps last known good only until `max_staleness`, then fails closed; it never falls back to source, env defaults, or unknown keys. | Refresh state machine; validated keyring; staleness check in every auth/sign path. | 503 `KEYRING_STALE`; outbound signing refuses; alert fired. | T-40, T-42 | All secret consumers |
| I-17 | No secret material appears in logs, errors, audit records, traces, metrics, or build artifacts; secrets come only from the deployment secret store. | Redacting secret wrapper; field allowlists; error serializer; CI secret scan; no secret fixtures/artifacts. | Build/test fails on scan; runtime responses/logs redact. | T-41 | Service, CI, build, artifacts |
| I-18 | For every invoice, stored subtotal/tax/total agree with the server-computed values from its lines and tax inputs, and all line currencies match the invoice currency. | Deferred constraint trigger on `invoices`/`invoice_lines`; server-side calculation; same transaction. | 422 or constraint abort; no inconsistent commit. | T-43 | Invoice create/update |
| I-19 | Configuration that would make the other invariants untestable or unsafe is rejected at startup. | Startup validation of retention, lease timeout, keyring staleness, and bypass flags. | Process exits nonzero; deployment does not start. | T-44 | Deployment configuration |

---

## 5. Invariant details

### I-01: No invoice access outside the effective tenant

- **Statement:** For every request, every invoice row and invoice-child row read, inserted, updated, or deleted has `tenant_id` equal to the request's effective tenant. No response contains data from another tenant, and no write affects a row in another tenant.
- **Enforcement point:** `authorize_invoice_action()` / `authorize_admin_action()` produce an opaque `TenantScope`; `InvoiceRepository` and worker commit functions accept only `TenantScope`; PostgreSQL RLS policies on `invoices`, `invoice_lines`, `invoice_idempotency`, `invoice_leases`, `outbox`, and `audit_events`. The application role is not the table owner and has no `BYPASSRLS`.
- **Failure mode:** Deny. A cross-tenant or missing object returns the same `404 INVOICE_NOT_FOUND` shape. Lists/searches/exports return only the effective tenant's rows. A write transaction aborts; no row outside the tenant is affected.
- **Paths covered:** REST, batch/import, admin, worker commit, outbox consumer, CLI maintenance, migration/restore.
- **Actors covered:** user, role-less, expired, revoked membership, neighboring-tenant user, admin without the target tenant grant, admin with a grant for a different tenant.
- **Concurrency:** Tenant context is transaction-local (`set_config(..., true)`); RLS is evaluated per statement. No session-level tenant setting is used, so pooled connections cannot leak context. The repository's tenant predicate is atomic with the tenant context.
- **Evidence:** T-01..T-06, T-10, T-17.
- **Scope:** Supported platform and all entry points in section 1.2.
- **Out of scope:** Direct operator access using a `BYPASSRLS` role; that path is separately gated and audited.
- **Residual risk:** RLS policy drift or a new tenant table without a policy. CI must assert that every tenant table has RLS enabled and forced, and the architecture test must reject raw SQL outside the repository.

### I-02: Tenant binding is immutable and referentially consistent

- **Statement:** An invoice's `tenant_id` cannot change after insert. Every line item, attachment, event, lease, idempotency record, and outbox row that references an invoice resolves to an invoice in the same tenant. No cross-tenant foreign key can be created.
- **Enforcement point:** `UNIQUE (tenant_id, id)` on `invoices`; composite foreign keys `(tenant_id, invoice_id)` on every child/reference table; `BEFORE UPDATE` trigger rejecting `NEW.tenant_id IS DISTINCT FROM OLD.tenant_id`; column-level grants that exclude `tenant_id` from application updates.
- **Failure mode:** Abort. The database rejects the statement; API returns 409/422 or a generic conflict; no partial write.
- **Paths covered:** API writes, batch/import, worker writes, migrations/backfills.
- **Actors covered:** All; an admin grant never permits moving an invoice between tenants.
- **Concurrency:** Composite FK and trigger checks are enforced by the database for every writer, including concurrent writers and maintenance jobs.
- **Evidence:** T-07.
- **Scope:** All tables that reference invoices.
- **Out of scope:** Deliberate tenant merge/migration, which must use a separately designed, audited procedure and preserve the creation-key tombstone.
- **Residual risk:** A future child table could omit the composite FK. Migration review and a schema test must require `(tenant_id, invoice_id)` on every invoice child table.

### I-03: Default-deny action authorization

- **Statement:** A user request may perform action `A` on tenant `T` only if the principal is authenticated, the session is active, membership in `T` is active, and `A` is in the principal's effective permissions for `T`. Unauthenticated, expired-session, revoked-membership, role-less, unknown-action, and missing-permission requests are denied before any invoice read or write.
- **Enforcement point:** `authenticate(request)` then `authorize_invoice_action(principal, action, tenant_id)` returns `TenantScope` or raises. The action is a closed enum (`invoice:read`, `invoice:create`, `invoice:update`, `invoice:delete`, `invoice:export`). No handler performs its own permission logic.
- **Failure mode:** Deny. 401 for missing/expired authentication; 403 for missing membership/permission; 404 when the action is allowed at route level but the object is outside the tenant (I-01). No business state changes; a denial audit event may be written.
- **Paths covered:** All user REST, search, export, batch/import paths.
- **Actors covered:** anonymous, expired session, revoked membership, role-less user, read-only user attempting write, user with an unknown role/permission, user from a neighboring tenant.
- **Concurrency:** Membership revocation is checked in the same transaction as the write; a revocation that commits before the request's transaction begins denies it. A request already authorized in a transaction may complete, and revocation is effective for subsequent transactions.
- **Evidence:** T-08, T-09, T-45.
- **Scope:** All normal user entry points.
- **Out of scope:** Admin authority, which is I-04, and tenant-wide ownership rules beyond membership (for example, "only the invoice creator may edit" if that policy is later required).
- **Residual risk:** If a permission cache is introduced, it must be versioned/revocable and fail closed; an unbounded cache is a check-then-act bug.

### I-04: Admin action requires an explicit, scoped grant

- **Statement:** A request on the admin invoice surface is allowed only if it presents a grant id and the server finds an `admin_grants` row where `admin_user_id = caller`, `tenant_id = target tenant`, `action = requested action`, `revoked_at IS NULL`, `not_before <= db_clock < expires_at`. The admin role alone, a wildcard tenant, a wildcard action, a grant for another tenant, a read-only grant used for a write, or a grant issued to another admin never authorizes.
- **Enforcement point:** `authorize_admin_action(principal, grant_id, tenant_id, action)` is a `SECURITY DEFINER` function with pinned `search_path`. It selects the grant `FOR SHARE` in the same transaction as the write, so a concurrent revocation cannot commit between the check and the write. The application role has no direct access to `admin_grants`. A database check `created_by <> admin_user_id` blocks self-grants.
- **Failure mode:** Deny. 403 `ADMIN_GRANT_REQUIRED` for missing/expired/revoked/wrong-scope grant; 503 `AUTHORIZATION_UNAVAILABLE` on grant-store error/timeout. No invoice read or write. Every admin decision is audited with the grant id.
- **Paths covered:** All `/admin` invoice endpoints and any code path acting with admin authority.
- **Actors covered:** admin with no grant, admin with an expired grant, admin with a revoked grant, admin with a not-yet-valid grant, admin with a grant for tenant A targeting tenant B, admin with a read grant attempting write, admin using another admin's grant id, admin attempting to create/extend a grant through the invoice API.
- **Concurrency:** Grant check and write share one transaction. Revocation takes a row lock that conflicts with `FOR SHARE`; a revocation committed before the transaction begins is seen, and an in-flight authorized transaction completes before revocation can take effect. The transaction timeout must be bounded by the grant's remaining validity.
- **Evidence:** T-11..T-16.
- **Scope:** Admin surface, admin batch (one tenant per request), and any future admin-authority path.
- **Out of scope:** Grant issuance service and approval workflow. The API treats grants as read-only.
- **Residual risk:** A compromised grant-issuance service could create valid grants. The `created_by <> admin_user_id` constraint prevents self-grants, but grant issuance must have its own invariant map, dual control, and audit.

### I-05: One set of choke points, no ambient bypass

- **Statement:** Every entry point that can read or write invoice data calls the same authorization function and the same repository/commit function. No environment flag, test hook, maintenance mode, raw SQL path, alternate endpoint, or "internal" caller bypasses tenant scope, action authorization, lease fencing, or audit.
- **Enforcement point:** Typed `TenantScope` with a private constructor; `InvoiceRepository` is the only code allowed to issue invoice SQL; architecture/static test over the route table and call graph; database role separation (`app_rw`, `app_worker`, `migrator`); startup configuration validation rejects known bypass flags.
- **Failure mode:** The process refuses to start with a bypass configuration. A request on an unregistered path is denied by default. A raw SQL call outside the repository fails the static test in CI. A migration/backfill path without a tenant scope fails the same checks.
- **Paths covered:** Every path in section 1.2, plus future endpoints.
- **Actors covered:** All.
- **Concurrency:** Not a concurrency property itself; it ensures the other invariants are reached by every concurrent path.
- **Evidence:** T-17, T-04, T-36.
- **Scope:** The deployed service and its migration tooling.
- **Out of scope:** Break-glass operator access, which is a named, separately gated path and must not be an ambient flag.
- **Residual risk:** New endpoints can be added without the test. The route table must be generated from the same source as the router; a new route with no authorization entry fails startup.

### I-06: Creation is idempotent for the lifetime of the invoice

- **Statement:** At most one invoice exists for a given `(tenant_id, creation_idempotency_key)`, for the lifetime of the invoice. A retry with the same key, principal, operation, and canonical request hash returns the original invoice and does not create another. The guarantee does not expire when the response-replay record is purged.
- **Enforcement point:** `UNIQUE (tenant_id, creation_idempotency_key)` on `invoices`; `creation_request_hash` and `created_by` on the invoice; `invoice_idempotency` primary key `(tenant_id, idempotency_key)` for response replay and in-progress coordination; one create transaction.
- **Failure mode:** On a valid retry: replay the original success with `Idempotency-Replayed: true`; no new invoice. On a conflicting reuse: 409, no new invoice. On an in-progress duplicate: 409 `IDEMPOTENCY_IN_PROGRESS` with `Retry-After`, no new invoice.
- **Paths covered:** `POST /v1/invoices`, batch create, import. Each imported invoice must carry or derive a stable creation key (`source_system:source_id`); the batch as a whole is one tenant and one transaction.
- **Actors covered:** Users, admins with grants, import jobs. The key is tenant-scoped; the same key in another tenant is a different key.
- **Concurrency:** The unique index is the arbiter. Concurrent inserts with the same key serialize on the index; exactly one commits. The loser either replays the committed invoice or returns 409. The server never uses an in-memory cache as the source of truth.
- **Evidence:** T-18, T-19, T-23, T-24, T-25.
- **Scope:** Invoice creation.
- **Out of scope:** A client that retries with a new key cannot be distinguished from a new request; the API contract requires key reuse for retries. See residual risk.
- **Residual risk:** If invoices are hard-deleted, the unique key disappears. Deletion must retain a tombstone (`deleted_at` plus the unique key, or a separate `invoice_creation_keys` table) or I-06 is broken. Client key generation must be high-entropy and stable per logical operation.

### I-07: Idempotency-key misuse is rejected without side effects

- **Statement:** If a key exists for `(tenant_id, idempotency_key)` and the new request has a different principal, operation, or canonical request hash, the request is rejected with 409 and the original invoice/idempotency record is unchanged. A tenant-scoped key never resolves to an invoice in another tenant.
- **Enforcement point:** Stored `principal_id`, `operation`, and `request_hash` compared after the unique conflict; `tenant_id` is part of the primary key. Canonicalization is explicit: sorted object keys, decimal values normalized to minor units, duplicate JSON keys rejected, unknown fields rejected.
- **Failure mode:** 409 `IDEMPOTENCY_KEY_REUSED`; rollback; no duplicate, no mutation, no cross-principal response.
- **Paths covered:** Create, update, batch/import.
- **Actors covered:** Same-tenant different user, different tenant, admin using a user's key, user replaying an admin key, operation mismatch (create vs update), payload mismatch.
- **Concurrency:** The unique constraint serializes all writers with the same key; the comparison happens on the committed record.
- **Evidence:** T-20, T-21, T-22.
- **Scope:** All mutation endpoints.
- **Out of scope:** Semantic equivalence of payloads that differ only in fields the API ignores; the canonical form is the contract and is documented in the API reference.
- **Residual risk:** A badly canonicalized payload can produce a false conflict or a false replay. The canonicalizer is covered by property/fuzz tests in addition to T-20.

### I-08: Updates are versioned and applied at most once per key

- **Statement:** An update commits only if its `expected_version` equals the stored `version`. Concurrent updates with the same expected version: at most one commits; the others get 409 and leave no write. A replay with the same idempotency key returns the original result and does not increment the version again.
- **Enforcement point:** `UPDATE invoices SET ..., version = version + 1 WHERE tenant_id = :tenant AND id = :id AND version = :expected_version`; idempotency record keyed by `(tenant_id, idempotency_key)` with the target id and expected version in the request hash; one transaction.
- **Failure mode:** 409 `VERSION_CONFLICT` (or 404 if the invoice is absent) and rollback; replay returns the stored success response without a second application.
- **Paths covered:** `PUT/PATCH /v1/invoices/{id}`, admin update, batch update.
- **Actors covered:** Users, admins, workers (workers use the same version predicate through `commit_worker_write`).
- **Concurrency:** The version predicate is the serialization mechanism; no read-then-write check in application code. Row locks are taken by the update itself.
- **Evidence:** T-26, T-27.
- **Scope:** All invoice updates.
- **Out of scope:** A deliberate second edit by a client that re-reads the new version; that is a new action, not a retry.
- **Residual risk:** A client that omits `If-Match`/`expected_version` must be rejected, not defaulted to "latest". The boundary validator enforces this.

### I-09: Mutations are atomic and failures are not success-shaped

- **Statement:** A mutation either commits the invoice change, its line changes, its success audit event, and its outbox event together, or commits none. Every refusal, validation error, authorization failure, version conflict, audit failure, outbox failure, or crash leaves no partial business state. Internal failure is not converted into a success-shaped empty result.
- **Enforcement point:** One database transaction per mutation; audit and outbox inserts in the same transaction; deferred constraints; no external side effect before commit; outbox dispatcher only after commit. The API error contract in section 6.9 maps every failure to an explicit 4xx/5xx.
- **Failure mode:** Rollback, then 4xx/5xx. No invoice, line, success audit, or outbox row remains. A dependency failure returns 503, never `200 []` or `200 {}`.
- **Paths covered:** Create, update, batch/import, worker commit.
- **Actors covered:** All.
- **Concurrency:** The transaction is the atomicity boundary; deferred constraints run before commit. A crash between statements rolls back on connection loss.
- **Evidence:** T-28, T-29, T-30, T-45.
- **Scope:** All mutations.
- **Out of scope:** External systems that consume the outbox; they must implement I-13 and their own idempotency.
- **Residual risk:** An external side effect performed before commit would break atomicity. Code review must reject any network call inside the mutation path before commit.

### I-10: Audit trail is complete and append-only

- **Statement:** Every committed invoice mutation has exactly one success audit event whose `request_id`, `tenant_id`, `actor_id`, `action`, `invoice_id`, and resulting `version` match the committed state. Every admin decision produces an audit event when the audit sink is available. No runtime role can update or delete audit rows, and an actor cannot erase or modify their own trail.
- **Enforcement point:** Single `audit_append()` channel; `audit_events` insert-only grants; trigger rejecting `UPDATE`, `DELETE`, and `TRUNCATE`; optional per-tenant hash chain exported to WORM storage. Admin events include `grant_id`; denial events include the attempted action but no object data from another tenant.
- **Failure mode:** For a successful mutation, audit failure aborts the transaction (503 `AUDIT_UNAVAILABLE`). For a denied request, audit failure still denies (never allows) and raises an alert; a denial event may be missing, which is itself visible. Audit rows cannot be removed by the actor.
- **Paths covered:** All invoice mutations and admin decisions.
- **Actors covered:** Users, admins, workers, operators (through the shared channel).
- **Concurrency:** Audit insert is in the mutation transaction, so the audit row and business row share a commit order. If a hash chain is used, per-tenant advisory locking or a sequence serializes appends; contention is bounded per tenant.
- **Evidence:** T-29, T-31.
- **Scope:** Invoice mutations, admin decisions, denials where the sink is available.
- **Out of scope:** Legal retention and audit export/immutability outside the database (WORM is an operational control).
- **Residual risk:** A table owner or superuser can bypass triggers. Runtime roles are not owners; operator break-glass is separately audited and out of scope.

### I-11: One live lease per invoice, monotonic fencing token

- **Statement:** At most one lease per invoice is live. A lease acquisition succeeds only when no lease exists or the existing lease is expired. A takeover replaces the holder and increments the fencing token; tokens are strictly monotonic per invoice and are never reused.
- **Enforcement point:** `invoice_leases` with `invoice_id` primary key and composite tenant FK; `acquire_invoice_lease()` atomic insert/upsert with `WHERE expires_at <= clock_timestamp()` and `fencing_token = old.fencing_token + 1`.
- **Failure mode:** 409 `LEASE_BUSY`; no lease row created and no token issued.
- **Paths covered:** Worker job start and any internal job that mutates invoices.
- **Actors covered:** Workers, retried jobs, duplicate schedulers.
- **Concurrency:** The primary key serializes acquisition; the expiry predicate ensures only one winner after a lease expires. All time comparisons use the database clock.
- **Evidence:** T-32.
- **Scope:** Worker execution.
- **Out of scope:** Distributed scheduling policy (which worker should run); this invariant only constrains who may write.
- **Residual risk:** Lease TTL must exceed the maximum expected pause before commit plus the commit timeout; T-44 validates configuration.

### I-12: A stale or expired worker cannot commit

- **Statement:** A worker write commits only if, in the same transaction as the write, the supplied fencing token equals the current token for the invoice, the holder id matches, the tenant matches, and `expires_at > clock_timestamp()`. A worker whose lease expired, was taken over, or was never current cannot commit any invoice, audit, or outbox change.
- **Enforcement point:** `commit_worker_write()` is the only worker write path. It takes `SELECT ... FOR UPDATE` on the lease row, checks holder/token/tenant/expiry, then applies the versioned invoice update and inserts audit/outbox. It is `SECURITY DEFINER` with pinned `search_path`; the worker role has `EXECUTE` only and no direct `UPDATE` on invoice tables. The transaction timeout is set below the remaining lease so a paused transaction cannot outlive the lease.
- **Failure mode:** 409 `LEASE_LOST`; full rollback; no business or audit/outbox change. The worker records the loss and stops.
- **Paths covered:** All worker writes, including retries and outbox consumers that mutate invoices.
- **Actors covered:** Worker with stale token, expired lease, wrong holder, wrong tenant, direct SQL caller, worker paused between check and write.
- **Concurrency:** The lease row lock serializes takeover and commit. A takeover increments the token, so even if the old worker resumes it cannot match. If a commit transaction is paused after the check, it holds the lease row lock; the transaction timeout aborts it before the lease can be legitimately outlived, and a takeover cannot proceed until the transaction ends.
- **Evidence:** T-33..T-36.
- **Scope:** All worker writes.
- **Out of scope:** External side effects before commit are prohibited; all external effects go through the outbox and I-13.
- **Residual risk:** A worker with direct database credentials outside the worker role could bypass the function; role separation and T-36 are the guard. Clock skew is avoided by using database time; lease TTL must still be longer than the maximum commit transaction.

### I-13: Worker side effects are idempotent per source event

- **Statement:** For a given `(tenant_id, invoice_id, operation, source_event_id)`, the worker applies the side effect at most once. Duplicate delivery of the same job or outbox event does not duplicate the effect.
- **Enforcement point:** `processed_worker_events` primary key on those four columns, inserted in the same transaction as the effect/result; outbox consumer uses the event id as `source_event_id`; downstream calls receive the same stable idempotency key.
- **Failure mode:** Duplicate delivery returns the recorded result or a no-op; no second effect and no error that would cause an infinite retry.
- **Paths covered:** Outbox consumers, job retries, duplicate scheduler delivery.
- **Actors covered:** Workers, retry machinery, at-least-once queues.
- **Concurrency:** The primary key serializes concurrent consumers of the same event; one inserts and applies, the other sees the conflict and returns the recorded result.
- **Evidence:** T-37.
- **Scope:** All worker side effects, including calls to external services.
- **Out of scope:** Downstream systems that ignore the supplied idempotency key; they must honor it.
- **Residual risk:** If a side effect is performed before the processed-event row commits, a crash can duplicate it. The order is: claim/process in one transaction, external call only after commit, with the stable key.

### I-14: New secrets become effective without a restart

- **Statement:** A newly published secret version is used for new signatures and new credential checks within 60 s of publication, without restarting any process, on every replica. No process serves indefinitely from a boot-time snapshot.
- **Enforcement point:** `SecretProvider` loads a versioned keyring at startup and refreshes by watch or 15 s poll; a validated refresh is swapped atomically; every auth/sign operation reads the current snapshot. Tenant API-key rows are read from the database (or a revocable cache) so rotation is effective without restart. All replicas use the same contract.
- **Failure mode:** If a refresh fails, keep the last known good keyring only within I-16's staleness bound; if a refresh is invalid, reject it and alert. Never accept an unknown key.
- **Paths covered:** Session/JWT signing and verification, tenant API-key authentication, webhook signing, any other secret consumer.
- **Actors covered:** All replicas, all tenants.
- **Concurrency:** Atomic pointer swap; requests in flight may finish with the snapshot they started with, which is permitted within the overlap window. New requests see the new snapshot within the SLO.
- **Evidence:** T-38.
- **Scope:** All secrets in the rotation table in section 6.8.
- **Out of scope:** Secrets managed by the database connection pooler; see section 1.4.
- **Residual risk:** Propagation can take up to 60 s; clients must tolerate both old and new keys during the overlap. A process that is partitioned from the secret store is handled by I-16.

### I-15: Old secrets are rejected after their retirement deadline

- **Statement:** After a key or credential's `retire_at`, no request authenticated or signed with it is accepted. Before `retire_at`, it may be accepted only during the configured overlap. There is no indefinite old-key acceptance and no "accept any known historical key" fallback.
- **Enforcement point:** Keyring `not_before <= now < retire_at`; tenant API key `revoked_at IS NULL AND now < retire_at`; rotation procedure sets the deadline and the overlap; verification paths enforce it. JWT sessions signed with a retired key fail verification and require reauthentication.
- **Failure mode:** 401 `CREDENTIAL_EXPIRED` or signature verification failure; no fallback to the old key after the deadline.
- **Paths covered:** All authentication and signature verification.
- **Actors covered:** Users, services, webhook consumers, tenant API clients, stale clients.
- **Concurrency:** Time checks use a single clock source (secret-store timestamps or database time); a small, documented skew allowance is the only tolerance. In-flight requests that started before the deadline may complete; new requests after it are denied.
- **Evidence:** T-39.
- **Scope:** All rotating secrets and credentials.
- **Out of scope:** Already-delivered webhook signatures verified by an external consumer after their own retention period; that consumer owns its verification window.
- **Residual risk:** A client that never refreshes its credential will fail after the deadline by design. The overlap must be at least the maximum client refresh interval plus deployment rollout time.

### I-16: Secret-store failure is fail-closed and bounded

- **Statement:** If the secret store is unavailable or returns an invalid keyring, the service continues with the last known good keyring only until `max_staleness`; after that, every secret-dependent authentication/signing operation fails closed. It never falls back to source code, environment defaults, fixture keys, or an undefined key.
- **Enforcement point:** Refresh state machine tracks `last_success`; every auth/sign path checks `now - last_success <= max_staleness`; keyring validation checks schema, unique kids, key material length, and `not_before < retire_at`; invalid refreshes are rejected atomically. Outbound signing refuses rather than signing with a key past retirement.
- **Failure mode:** 503 `KEYRING_STALE` for authentication/signing; alert and metric; no static fallback. If the last known good keyring is still valid and within staleness, it is used.
- **Paths covered:** All secret consumers.
- **Actors covered:** All.
- **Concurrency:** The state machine is atomic; a failed refresh never partially replaces the keyring. Existing requests using a still-valid snapshot may finish.
- **Evidence:** T-40, T-42.
- **Scope:** All secret consumers.
- **Out of scope:** A deliberate emergency static key; none is allowed because it would violate the invariant.
- **Residual risk:** This is an availability tradeoff: a prolonged secret-store outage stops authentication. The alternative—accepting stale or unknown keys—would violate rotation and is not permitted.

### I-17: Secret material never leaks

- **Statement:** No secret material—key bytes, API keys, bearer tokens, signing secrets, or derived values—appears in logs, error responses, audit events, traces, metrics, fixtures, source, build artifacts, or API responses. Secrets are loaded only from the deployment secret store.
- **Enforcement point:** A `Secret<T>` wrapper whose debug/serialization methods redact; field-allowlist logging; error serializer that emits only code/message/request id; audit event field allowlist; CI secret scanning, including build artifacts; no secrets in test fixtures (tests generate ephemeral canaries).
- **Failure mode:** Runtime redaction; CI fails the build/release on a detected secret; the service does not start if a required secret is missing from the store (it does not fall back to source/env).
- **Paths covered:** All service components, CI, build, release.
- **Actors covered:** All; a user-triggered error cannot expose a server secret.
- **Concurrency:** Not applicable.
- **Evidence:** T-41.
- **Scope:** Service, tests, CI, artifacts.
- **Out of scope:** OS-level memory dumps, swap, and an operator with host root. Zeroization is best effort and cannot be guaranteed by managed runtimes.
- **Residual risk:** Crash dumps and core files can contain secrets; they are excluded from collection and access-controlled. Language runtimes may copy secret buffers; use byte arrays and wipe on completion where possible, but do not claim guaranteed zeroization.

### I-18: Invoice totals are internally consistent

- **Statement:** For every committed invoice, `subtotal_minor` equals the sum of its line amounts, `total_minor` equals `subtotal_minor + tax_minor`, and every line's currency equals the invoice currency. No update leaves an inconsistent total.
- **Enforcement point:** Server-side calculation in the same transaction; deferred constraint trigger on `invoice_lines` and `invoices`; `CHECK` constraints for non-negative amounts and currency format; line currency equality check.
- **Failure mode:** 422 or constraint abort; rollback; no inconsistent invoice commit.
- **Paths covered:** Create, update, batch/import, worker total recalculation.
- **Actors covered:** All writers, including admins and workers.
- **Concurrency:** Deferred constraints check at commit, so line inserts and total updates in the same transaction are consistent; concurrent transactions serialize on the invoice row/version.
- **Evidence:** T-43.
- **Scope:** Invoice amount fields in this API.
- **Out of scope:** Tax rules, discounts, rounding policy, and multi-currency conversion; those need their own invariants.
- **Residual risk:** A future line type or tax rule can invalidate the formula. The constraint must be updated with a migration and the negative test rerun on migrated data.

### I-19: Unsafe configuration is rejected at startup

- **Statement:** Configuration that makes an invariant impossible—`idempotency_retention < max_client_retry_window`, `lease_ttl <= worker_commit_timeout`, `keyring_max_staleness <= keyring_refresh_interval`, missing secret-store identity, or any known bypass flag—prevents the service from starting.
- **Enforcement point:** Startup validator with hard failures; deployment manifest schema; CI config test.
- **Failure mode:** Process exits nonzero before serving traffic; deployment rolls back. No degraded mode that silently disables an invariant.
- **Paths covered:** All deployments and replicas.
- **Actors covered:** Operators, deployment automation.
- **Concurrency:** Not applicable.
- **Evidence:** T-44, T-17.
- **Scope:** Runtime configuration and deployment manifests.
- **Out of scope:** Platform-level misconfiguration (for example, disabling RLS after startup); CI/database policy checks cover that.
- **Residual risk:** A config value can be safe at startup and changed later only by a restart, which revalidates.

---

## 6. Enforcement-point contracts

The code below is the implementation contract. Signatures and predicates matter; exact syntax can be adapted to the service language, but the database-side checks must remain in the database.

### 6.1 Request pipeline

```text
request
  -> validate transport, request id, body size
  -> authenticate()                         # 401 on failure
  -> route action and tenant
  -> if admin surface: authorize_admin_action(principal, grant_id, tenant, action)
     else:             authorize_invoice_action(principal, action, tenant)
  -> TenantScope (opaque; private constructor)
  -> handler calls InvoiceRepository / WorkerCommit with TenantScope
  -> one transaction:
       set_config('app.tenant_id', scope.tenant_id, true)
       set_config('app.principal_id', scope.principal_id, true)
       authorize is re-checked/locked in this transaction where applicable
       mutation + audit + outbox
     commit
```

`TenantScope` carries `tenant_id`, `principal_id`, `actor_kind` (user/admin/worker), and `grant_id` for admin. It is the only type the repository accepts. It is not constructible from request data.

`authorize_invoice_action()` rules:

```text
if principal is null or session inactive: raise 401
if principal has no active membership in tenant: raise 403
if action not in effective permissions: raise 403
return TenantScope(tenant, principal, actor_kind=user)
```

The action enum is closed. Unknown action -> 403, never "no policy, allow". If the membership source is unavailable -> 503, never allow.

### 6.2 Tenant scope and RLS

```sql
CREATE TABLE invoices (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  status text NOT NULL,
  currency char(3) NOT NULL,
  subtotal_minor bigint NOT NULL,
  tax_minor bigint NOT NULL,
  total_minor bigint NOT NULL,
  version bigint NOT NULL DEFAULT 1,
  creation_idempotency_key text NOT NULL,
  creation_request_hash bytea NOT NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  deleted_at timestamptz,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, creation_idempotency_key),
  CHECK (version > 0)
);

CREATE TABLE invoice_lines (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  amount_minor bigint NOT NULL,
  currency char(3) NOT NULL,
  FOREIGN KEY (tenant_id, invoice_id)
    REFERENCES invoices (tenant_id, id) ON DELETE CASCADE
);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;

CREATE POLICY invoices_tenant ON invoices
  USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE invoice_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_lines FORCE ROW LEVEL SECURITY;

CREATE POLICY invoice_lines_tenant ON invoice_lines
  USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
```

The same `ENABLE`/`FORCE`/policy pattern applies to `invoice_idempotency`, `invoice_leases`, `outbox`, `processed_worker_events`, and `audit_events`. `admin_grants` is not directly accessible to the application role; it is reached only through the grant-check function.

The application role is not the table owner, has no `BYPASSRLS`, and has no `TRUNCATE`. Tenant context is set only with transaction-local `set_config(..., true)`; no session-level `SET` is permitted. An unset `app.tenant_id` evaluates to `NULL`, and `tenant_id = NULL` is not true, so the policy denies.

Tenant immutability:

```sql
CREATE FUNCTION reject_invoice_tenant_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'invoice tenant_id is immutable';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER invoices_tenant_immutable
BEFORE UPDATE ON invoices
FOR EACH ROW EXECUTE FUNCTION reject_invoice_tenant_change();
```

The application gets column-level update rights that exclude `tenant_id`; the trigger is defense in depth. All child tables use the composite FK shown above. `invoice_leases`, `invoice_idempotency`, and `processed_worker_events` also use `(tenant_id, invoice_id)` foreign keys, never a bare `invoice_id`.

### 6.3 Admin grant check

```sql
CREATE TABLE admin_grants (
  id uuid PRIMARY KEY,
  admin_user_id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  action text NOT NULL CHECK (action IN
    ('invoice:read','invoice:create','invoice:update','invoice:delete','invoice:export')),
  not_before timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_by uuid NOT NULL,
  reason text NOT NULL,
  CHECK (expires_at > not_before),
  CHECK (created_by <> admin_user_id)
);

CREATE FUNCTION authorize_admin_grant(
  p_admin_user_id uuid,
  p_grant_id uuid,
  p_tenant_id uuid,
  p_action text
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
  v_grant_id uuid;
BEGIN
  SELECT id INTO v_grant_id
  FROM admin_grants
  WHERE id = p_grant_id
    AND admin_user_id = p_admin_user_id
    AND tenant_id = p_tenant_id
    AND action = p_action
    AND revoked_at IS NULL
    AND clock_timestamp() >= not_before
    AND clock_timestamp() < expires_at
  FOR SHARE;

  IF v_grant_id IS NULL THEN
    RAISE EXCEPTION 'ADMIN_GRANT_REQUIRED' USING ERRCODE = '42501';
  END IF;
  RETURN v_grant_id;
END;
$$;
```

Rules:

- The admin request must carry `X-Admin-Grant: <grant_id>`. A missing header is 403, even if the admin has an active grant.
- The grant is not a bearer token: the function also matches `admin_user_id`, tenant, and action.
- No wildcard tenant, no wildcard action. Batch admin work is one tenant per transaction with one grant.
- `FOR SHARE` prevents a revocation `UPDATE` from committing between the check and the write. A revocation that committed before the transaction begins is visible and denies. An in-flight transaction may complete; the transaction timeout is bounded by the grant's remaining validity.
- Grant-store error/timeout -> 503 `AUTHORIZATION_UNAVAILABLE`, not 403/allow.
- The application role has no direct `SELECT/INSERT/UPDATE/DELETE` on `admin_grants`. Grant issuance is out of scope, but self-grant is blocked by the check constraint and must be blocked by the grant service.

### 6.4 Idempotent creation and update

```sql
CREATE TABLE invoice_idempotency (
  tenant_id uuid NOT NULL,
  idempotency_key text NOT NULL,
  principal_id uuid NOT NULL,
  operation text NOT NULL,
  request_hash bytea NOT NULL,
  invoice_id uuid,
  response_status int,
  response_body jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key),
  FOREIGN KEY (tenant_id, invoice_id) REFERENCES invoices (tenant_id, id)
);
```

Create transaction:

```text
BEGIN
set_config('app.tenant_id', scope.tenant_id, true)
set_config('app.principal_id', scope.principal_id, true)

INSERT INTO invoice_idempotency
  (tenant_id, idempotency_key, principal_id, operation, request_hash, expires_at)
VALUES (..., 'create', ..., now() + retention)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING tenant_id;

if row was inserted:
    INSERT INTO invoices
      (..., creation_idempotency_key, creation_request_hash, created_by)
    VALUES (...)
    ON CONFLICT (tenant_id, creation_idempotency_key) DO NOTHING
    RETURNING id;

    if no invoice row:                       -- response row was purged, invoice remains
        SELECT id, created_by, creation_request_hash
          INTO existing
          FROM invoices
         WHERE tenant_id = scope.tenant_id
           AND creation_idempotency_key = key;
        if created_by != principal or creation_request_hash != hash:
            ROLLBACK; return 409 IDEMPOTENCY_KEY_REUSED
        UPDATE invoice_idempotency
           SET invoice_id = existing.id,
               response_status = 200,
               response_body = to_jsonb(existing)
         WHERE tenant_id = scope.tenant_id AND idempotency_key = key;
        COMMIT; return 200 with existing invoice and Idempotency-Replayed: true

    INSERT invoice_lines
    INSERT audit_events (decision = success, ...)
    INSERT outbox (event_id, ...)
    UPDATE invoice_idempotency
       SET invoice_id = ..., response_status = 201, response_body = ...
     WHERE tenant_id = ... AND idempotency_key = ...;
    COMMIT; return 201

else:
    SELECT * FROM invoice_idempotency
     WHERE tenant_id = scope.tenant_id AND idempotency_key = key
     FOR UPDATE;

    if principal_id != scope.principal_id
       or operation != 'create'
       or request_hash != hash:
        ROLLBACK; return 409 IDEMPOTENCY_KEY_REUSED

    if response_status IS NULL:
        ROLLBACK; return 409 IDEMPOTENCY_IN_PROGRESS + Retry-After

    COMMIT; return response_status, response_body, Idempotency-Replayed: true
```

The `UNIQUE (tenant_id, creation_idempotency_key)` on `invoices` is the durable duplicate guard. The idempotency table is the replay/coordination record. Purging the table does not permit a duplicate invoice; the create path falls back to the invoice row and compares the stored hash/creator.

Update transaction: same claim pattern, then:

```sql
UPDATE invoices
SET status = :status,
    currency = :currency,
    subtotal_minor = :subtotal,
    tax_minor = :tax,
    total_minor = :total,
    version = version + 1,
    updated_at = clock_timestamp()
WHERE tenant_id = :tenant_id
  AND id = :invoice_id
  AND version = :expected_version
RETURNING version;
```

If no row is updated, distinguish `404` (invoice absent in this tenant) from `409 VERSION_CONFLICT` with a read-only lookup; both leave no write. The request hash includes `operation = 'update:<invoice_id>'` and `expected_version`, so the same key cannot be replayed against a different invoice or version.

### 6.5 Error contract at the mutation boundary

The boundary validator rejects missing `Idempotency-Key` before opening a transaction. Key length is 16..128 printable characters; high-entropy generation is the client's responsibility. Missing, malformed, or overlong keys -> 400 `IDEMPOTENCY_KEY_REQUIRED` / `IDEMPOTENCY_KEY_INVALID`, no invoice/claim. The canonical body is validated once at the boundary; deeper layers do not reparse untrusted input.

All mutation handlers return the error table in section 6.9. A handler that cannot classify an internal failure returns 500 with no state change; it never returns `200` with an empty result.

### 6.6 Lease acquisition and fencing

```sql
CREATE TABLE invoice_leases (
  invoice_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  holder_id uuid NOT NULL,
  fencing_token bigint NOT NULL CHECK (fencing_token > 0),
  expires_at timestamptz NOT NULL,
  FOREIGN KEY (tenant_id, invoice_id) REFERENCES invoices (tenant_id, id)
);

CREATE FUNCTION acquire_invoice_lease(
  p_tenant_id uuid,
  p_invoice_id uuid,
  p_holder_id uuid,
  p_ttl interval
) RETURNS TABLE (fencing_token bigint, expires_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
BEGIN
  RETURN QUERY
  INSERT INTO invoice_leases AS l
    (invoice_id, tenant_id, holder_id, fencing_token, expires_at)
  SELECT i.id, i.tenant_id, p_holder_id, 1, clock_timestamp() + p_ttl
  FROM invoices i
  WHERE i.id = p_invoice_id
    AND i.tenant_id = p_tenant_id
  ON CONFLICT (invoice_id) DO UPDATE
    SET holder_id = EXCLUDED.holder_id,
        fencing_token = l.fencing_token + 1,
        expires_at = EXCLUDED.expires_at
    WHERE l.expires_at <= clock_timestamp()
  RETURNING l.fencing_token, l.expires_at;
END;
$$;
```

`acquire_invoice_lease` returns no row when the invoice does not exist in the tenant or an unexpired lease exists. The caller maps that to 404 or 409 `LEASE_BUSY`. The lease row is never deleted; it is the durable record of the highest fencing token.

Worker commit:

```sql
CREATE FUNCTION commit_worker_write(
  p_tenant_id uuid,
  p_invoice_id uuid,
  p_holder_id uuid,
  p_fencing_token bigint,
  p_expected_version bigint,
  p_payload jsonb
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
  v_lease invoice_leases%ROWTYPE;
  v_version bigint;
BEGIN
  SELECT * INTO v_lease
  FROM invoice_leases
  WHERE invoice_id = p_invoice_id
    AND tenant_id = p_tenant_id
  FOR UPDATE;

  IF NOT FOUND
     OR v_lease.holder_id <> p_holder_id
     OR v_lease.fencing_token <> p_fencing_token
     OR v_lease.expires_at <= clock_timestamp() THEN
    RAISE EXCEPTION 'LEASE_LOST' USING ERRCODE = '40001';
  END IF;

  PERFORM set_config(
    'statement_timeout',
    greatest(
      1,
      floor(extract(epoch FROM (v_lease.expires_at - clock_timestamp())) * 1000)::int - 1000
    )::text,
    true
  );

  UPDATE invoices
  SET status = (p_payload->>'status'),
      subtotal_minor = (p_payload->>'subtotal_minor')::bigint,
      tax_minor = (p_payload->>'tax_minor')::bigint,
      total_minor = (p_payload->>'total_minor')::bigint,
      version = version + 1,
      updated_at = clock_timestamp()
  WHERE id = p_invoice_id
    AND tenant_id = p_tenant_id
    AND version = p_expected_version
  RETURNING version INTO v_version;

  IF v_version IS NULL THEN
    RAISE EXCEPTION 'VERSION_CONFLICT' USING ERRCODE = '40001';
  END IF;

  INSERT INTO audit_events (...);
  INSERT INTO outbox (...);
  RETURN v_version;
END;
$$;
```

The worker role gets only `EXECUTE ON FUNCTION commit_worker_write(...)` and `acquire_invoice_lease(...)`. It has no `UPDATE`/`INSERT` on `invoices`, `invoice_lines`, `audit_events`, or `outbox`. A stale worker that calls the function after a takeover fails the token comparison; one whose lease expired fails the expiry comparison; one that pauses before calling the function is simply stale. A transaction that pauses inside the function holds the lease row lock, and the statement timeout computed from the remaining lease aborts it before it can outlive the lease.

### 6.7 Audit and outbox

```sql
CREATE TABLE audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  actor_kind text NOT NULL,
  action text NOT NULL,
  decision text NOT NULL,
  invoice_id uuid,
  request_id uuid NOT NULL,
  grant_id uuid,
  version bigint,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM app_rw, app_worker;
GRANT INSERT, SELECT ON audit_events TO app_rw;

CREATE FUNCTION deny_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$;

CREATE TRIGGER audit_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION deny_audit_mutation();
```

`audit_append()` is the only writer. It takes a closed event type, a request id, and scalar fields; it never accepts a raw request/response blob, headers, tokens, or free-form error text. A denial event may omit `invoice_id` when the object is outside the tenant; it must not echo the other tenant's data. For a successful mutation, the audit row is inserted in the same transaction as the invoice update, so the transaction cannot commit without it. If the audit append fails, the mutation aborts and returns 503 `AUDIT_UNAVAILABLE`; a denied request remains denied and an alert is raised if its denial event cannot be written.

`outbox` is likewise inserted in the mutation transaction with a stable `event_id` and `(tenant_id, invoice_id, operation)`. Dispatch happens only after commit. The dispatcher marks the row sent; duplicate dispatch is handled by I-13 on the consumer side.

### 6.8 Secret rotation

Secret classes in scope:

| Secret class | Storage | Rotation effect | Old credential after `retire_at` |
| --- | --- | --- | --- |
| Session/JWT signing key | versioned keyring from secret store | New signatures use `current_kid`; verifiers accept `not_before <= now < retire_at`. | Signature verification fails; session must reauthenticate. |
| Tenant API key | `tenant_api_keys` row with hash, `not_before`, `retire_at`, `revoked_at` | New key row is active immediately; old row gets `retire_at`. | 401 `CREDENTIAL_EXPIRED`. |
| Webhook signing secret | versioned keyring/secret record | New outbound signatures use current version; consumers verify overlap. | Signature verification fails after retirement. |

```sql
CREATE TABLE tenant_api_keys (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  key_hash bytea NOT NULL UNIQUE,
  not_before timestamptz NOT NULL,
  retire_at timestamptz,
  revoked_at timestamptz
);

CREATE TABLE keyring_state (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  version text NOT NULL,
  payload jsonb NOT NULL,
  last_success_at timestamptz NOT NULL
);
```

The keyring payload is validated before swap:

```text
keyring = {
  version: string,
  current_kid: string,
  keys: [{
    kid: string, alg: string, material: bytes,
    not_before: timestamp, retire_at: timestamp
  }]
}
```

Validation requires unique `kid`, at least one key valid now, `not_before < retire_at`, an allowed algorithm, and key material of the expected length. An invalid refresh is rejected; the last good keyring remains active only within `max_staleness`. Every auth/sign call checks staleness before using the snapshot.

Rotation procedure:

1. Publish the new key version with `not_before = now`, `retire_at = null` (or a far future time).
2. Wait until the rotation SLO has elapsed and every replica reports the new version.
3. Set the old key's `retire_at = now + overlap` and the new key as `current_kid`.
4. After `retire_at`, old signatures/credentials fail. No restart is involved at any step.

No fallback to `AUTH_SECRET`, fixture keys, or a default key exists in any environment. A missing secret-store identity is a startup failure (I-19), not a degraded mode.

### 6.9 Error contract and fail-closed behavior

| Condition | HTTP | Code | Business state change |
| --- | --- | --- | --- |
| Missing/invalid/expired authentication | 401 | `AUTH_REQUIRED` / `SESSION_EXPIRED` | none |
| Authenticated, no membership/permission | 403 | `FORBIDDEN` | none |
| Admin grant missing/expired/revoked/wrong scope | 403 | `ADMIN_GRANT_REQUIRED` | none |
| Grant store unavailable/timeout | 503 | `AUTHORIZATION_UNAVAILABLE` | none |
| Invoice absent in effective tenant, or cross-tenant object | 404 | `INVOICE_NOT_FOUND` | none |
| Missing/malformed idempotency key | 400 | `IDEMPOTENCY_KEY_REQUIRED` / `IDEMPOTENCY_KEY_INVALID` | none |
| Same key, different principal/operation/payload | 409 | `IDEMPOTENCY_KEY_REUSED` | none |
| Same key currently in progress | 409 | `IDEMPOTENCY_IN_PROGRESS` | none |
| Stale version | 409 | `VERSION_CONFLICT` | none |
| Stale/expired lease | 409 | `LEASE_LOST` | none |
| Audit unavailable | 503 | `AUDIT_UNAVAILABLE` | none (rollback) |
| Outbox unavailable | 503 | `OUTBOX_UNAVAILABLE` | none (rollback) |
| Keyring stale/invalid | 503 | `KEYRING_STALE` | none |
| Retired credential | 401 | `CREDENTIAL_EXPIRED` | none |
| Validation failure | 422 | `VALIDATION_FAILED` | none |
| Unexpected internal failure | 500 | `INTERNAL_ERROR` | none |

Fail-closed matrix:

| Dependency or condition | Behavior |
| --- | --- |
| Membership store unavailable | 503; deny. |
| Unknown role/action | 403; deny. |
| Admin grant store unavailable | 503; deny. |
| Tenant context missing or empty | RLS returns zero rows / rejects writes. |
| Idempotency store unavailable | 503; no invoice. |
| Audit store unavailable | Mutation aborts; denial stays denied. |
| Outbox store unavailable | Mutation aborts; no event. |
| Lease store unavailable | Worker aborts; no write. |
| Secret store unavailable | Last known good only until `max_staleness`; then 503. |
| Malformed keyring | Reject refresh, keep last known good, alert; then 503 after max staleness. |

Error responses contain only `code`, a stable user-facing message, and `request_id`. They never contain stack traces, SQL, table names, key material, tokens, or another tenant's identifiers.

---

## 7. Negative test catalogue

### 7.1 Conventions

- Every test is written before the enforcement and is run twice: once normally (must pass) and once with the guard removed or replaced by a no-op (must fail). A test that cannot fail is not evidence.
- `DBΔ=0` means no change to `invoices`, `invoice_lines`, `invoice_idempotency`, `invoice_leases`, `processed_worker_events`, or `outbox`. A denial audit event may be appended; tests that assert audit content say so.
- `DBΔ=expected` means the stated rows exist and no extra invoice/outbox/audit success row exists.
- Concurrency tests use two independent database connections and, where stated, two application instances. Never rely on a single-threaded in-process queue.
- Test hooks: `pause_before_commit`, `pause_before_worker_commit`, `fail_audit_insert`, `fail_outbox_insert`, `fail_grant_lookup`, `fake_secret_store`, `fake_clock`. Hooks are available only in test builds and cannot be enabled by an environment flag in production (T-17).
- The database is reset between tests; fixtures include at least tenants A and B, users with different roles, invoices in both tenants, and a canary secret that must never appear in output.
- Assertions check the oracle, not only the HTTP status: row counts, version values, audit fields, outbox payload, absence of another tenant's identifiers, and response schema.

### 7.2 Authorization and tenant-isolation tests

| ID | Invariant | Setup -> action | Expected assertion | Guard removal (paired run must fail) |
| --- | --- | --- | --- | --- |
| T-01 | I-01 | User A (member of tenant A) requests `GET /v1/invoices/{invoiceB}`. | 404 `INVOICE_NOT_FOUND`; body has no B id, amount, or metadata; `DBΔ=0`; a denial audit, if present, has tenant A and no B fields. | Remove the repository tenant predicate or drop the RLS policy: response becomes 200 with B data. |
| T-02 | I-01 | A has two invoices, B has three. A calls list, search, and export. | Only A's two invoices appear; counts and totals equal A's; no B id, amount, or metadata in body/CSV; `DBΔ=0`. | Remove tenant filtering: B rows appear in list/search/export. |
| T-03 | I-01, I-09 | A sends `PUT`, `PATCH`, and (if enabled) `DELETE` for B's invoice. | 404; B version, lines, audit, and outbox unchanged; no partial write; `DBΔ=0`. | Skip the tenant scope on writes: B's version increments or row is deleted. |
| T-04 | I-01, I-05 | A submits a batch/import containing one A item and one B item. | Whole request is 4xx (generic tenant-mismatch error); zero invoices/lines/outbox rows for both items; A-only retry succeeds. | Apply per-item filtering or write items before the batch check: B row is created. |
| T-05 | I-01, I-05 | On one pooled connection: A request completes, then B request; separately call the repository with no scope and run direct SQL as `app_rw` with no `app.tenant_id`. | B request sees only B; unscoped repository raises; direct SQL returns zero rows and insert fails; context does not leak across pooled requests. | Use session-level `SET app.tenant_id` or disable RLS: A's context leaks into B or unscoped SQL sees rows. |
| T-06 | I-01, I-03 | Route-level auth permits A to use the generic invoice endpoint; the object id belongs to B. | 404, not 200/403; object-level check is visible; `DBΔ=0`. | Remove the object-level tenant predicate and rely only on route action: A receives B's invoice. |
| T-07 | I-02 | Direct SQL: `UPDATE invoices SET tenant_id=B WHERE id=A_invoice`; insert an `invoice_lines` row with `tenant_id=B` and an A invoice id; API update body includes `tenant_id=B`. | Update is rejected by trigger/privilege; line insert fails composite FK; API ignores/rejects tenant change; no row changes. | Drop the trigger/composite FK or grant column update: tenant move or cross-tenant child succeeds. |
| T-08 | I-03 | Requests with no token, expired token, revoked membership, role-less user, unknown action. | 401 for authentication cases, 403 for membership/action cases; `DBΔ=0`; batch behaves the same. | Replace auth with a no-op or treat missing role as allow: request returns 200. |
| T-09 | I-03 | A read-only user calls GET (allowed) then POST/PATCH (not allowed). | GET 200; POST/PATCH 403; no invoice/line/outbox change. | Remove the action-permission check and check only authentication: write succeeds. |
| T-10 | I-01 | A sends `tenant_id=B` in query, header, and body while authenticated for A; separately changes the path tenant to B. | Client-supplied tenant is ignored or rejected; only A data is returned; path B returns 404; no B data. | Trust the client tenant/header: B data is returned or written. |
| T-11 | I-04 | Admin role present, no `X-Admin-Grant` header; call admin read and admin write. | 403 `ADMIN_GRANT_REQUIRED`; no invoice/line/outbox change; no B data. | Treat the admin role as sufficient: request returns 200. |
| T-12 | I-04 | Grant matrix: read-only grant used for write; grant for tenant A used for B; expired; revoked; not-yet-valid; grant issued to another admin; wildcard/unknown action; grant with `created_by = admin_user_id` inserted directly. | All are 403 (or DB check rejection for self-grant); `DBΔ=0`; no cross-tenant data. | Ignore any one dimension (action, tenant, time, actor, revocation): that case succeeds. |
| T-13 | I-04 | `fail_grant_lookup` simulates timeout/unavailable grant store; admin read and write attempt. | 503 `AUTHORIZATION_UNAVAILABLE`; no invoice read/write; no fallback to role. | Catch the grant-store error and allow: request succeeds. |
| T-14 | I-04 | Admin has grant A, requests invoice B with grant A; then gets a valid grant B and requests B. | First request 403/404 with no B data; second succeeds only if grant B matches tenant/action; RLS still scopes to B. | Do not bind grant to target tenant: grant A reads/writes B. |
| T-15 | I-04 | Call `POST /v1/admin/grants` (or any grant-create route) as admin; direct insert into `admin_grants` with `created_by = admin_user_id`; try to extend own grant through invoice API. | 404/403 on API; DB check rejects self-grant; grant table unchanged. | Expose a grant-create route or drop the self-grant check: grant is created. |
| T-16 | I-04 | Admin authenticates, pauses before the write transaction; revoke the grant and commit; resume. Also test a revocation arriving while an already-authorized transaction holds the grant row. | Resumed request 403, no write. An in-flight transaction that already holds `FOR SHARE` completes, and revocation is effective for the next transaction; no write occurs after a revocation that committed before the transaction began. | Cache the grant decision or check once without a lock: request writes after revocation. |
| T-17 | I-05 | Static/architecture test: enumerate routes and call graph; grep for raw invoice SQL outside repository; start service with `BYPASS_AUTH=1`, `BYPASS_TENANT=1`, or a test-only raw path; runtime-call every entry point with a neighboring tenant. | Static test reports every route authorized and no raw SQL; startup fails on bypass config; all entry points deny neighbor access. | Add one raw SQL path or remove startup validation: static/config test fails; neighbor access succeeds. |

### 7.3 Idempotency, update, and atomicity tests

| ID | Invariant | Setup -> action | Expected assertion | Guard removal (paired run must fail) |
| --- | --- | --- | --- | --- |
| T-18 | I-06 | Create invoice with key K and body B; repeat the exact request after the first commits. | First 201; second 200 with `Idempotency-Replayed: true`; both return the same invoice id; exactly one invoice and one creation-key row. | Drop the invoice unique key or replay comparison: second request creates a duplicate. |
| T-19 | I-06 | 50 concurrent creates with the same key/body across two application instances. | Exactly one invoice; all success responses carry the same id or 409 `IDEMPOTENCY_IN_PROGRESS`; no duplicate invoice/line; one idempotency row. | Drop the unique constraint: more than one invoice exists. |
| T-20 | I-07 | Create with key K and amount 100; retry with key K and amount 200; retry with reordered equivalent JSON of amount 100. | Different amount -> 409 `IDEMPOTENCY_KEY_REUSED`, original unchanged; equivalent canonical body -> replay, not a new invoice. | Compare only the key, or skip canonicalization: original is overwritten or a duplicate is created. |
| T-21 | I-07 | Same key/body used by a different principal in the same tenant; separately by an admin; separately by a user in another tenant. | Same tenant/different principal -> 409, no replay/leak; different tenant -> independent key, never returns tenant A's invoice. | Skip principal check: B receives A's invoice or a duplicate is created. |
| T-22 | I-07 | Same key K used in tenant A and tenant B. | Two invoices, one per tenant; A retry returns only A's invoice; B retry returns only B's; cross-tenant read is 404. | Make the key globally unique: tenant B conflicts with A or resolves to A's invoice. |
| T-23 | I-06 | Missing key, 1-character key, 129-character key, non-printable key. | 400 `IDEMPOTENCY_KEY_REQUIRED`/`IDEMPOTENCY_KEY_INVALID`; no invoice or idempotency row. | Make the key optional: invoice is created without it. |
| T-24 | I-06, I-09 | Inject failure after the invoice insert but before commit; retry the same key. | First request rolls back all rows; retry succeeds exactly once; no orphan claim/audit/outbox. | Commit the claim/invoice in a separate transaction: retry is blocked or produces a duplicate. |
| T-25 | I-06 | Delete the `invoice_idempotency` response row (simulate retention expiry); retry same key/body; retry same key/different body. | Same body -> no duplicate; returns existing invoice (or 409 with stable explanation); different body -> 409; invoice count remains one. | Rely only on the purgeable idempotency table: retry creates a second invoice. |
| T-26 | I-08 | Two concurrent updates to the same invoice with the same `expected_version`, different payloads. | One 200; one 409 `VERSION_CONFLICT`; final row equals the winner; version increments exactly once; one audit/outbox success. | Remove the version predicate: both updates succeed or the loser overwrites the winner. |
| T-27 | I-08 | Update with key U, then repeat U with same body; repeat U with different body. | Same body returns original response and version increments once; different body 409; no second audit/outbox. | Replay reapplies the update: version increments twice or state changes. |
| T-28 | I-09 | Send invalid payload, unauthorized request, version-conflict update, and missing-key create; inspect all tables after each. | All fail with the contract code; `DBΔ=0` for business tables; no partial line, success audit, or outbox row. | Write the invoice before validation/authorization: a partial row remains. |
| T-29 | I-09, I-10 | `fail_audit_insert` during create and update. | 503 `AUDIT_UNAVAILABLE`; invoice/lines/outbox rolled back; no success audit; retry works. A denied request remains denied if denial audit fails. | Catch and ignore the audit failure: invoice commits without an audit event. |
| T-30 | I-09 | `fail_outbox_insert` during create and update. | 503 `OUTBOX_UNAVAILABLE`; invoice/lines/audit rolled back; outbox empty; no external event is published. | Publish after commit or ignore the outbox failure: invoice exists without an event. |
| T-31 | I-10 | As `app_rw`, attempt `UPDATE audit_events SET decision='denied'` and `DELETE FROM audit_events`; call any API delete route as the actor/admin; inspect audit row. | Permission/trigger denies both SQL operations; API has no delete; audit decision/row unchanged; hash chain (if enabled) detects tampering. | Grant update/delete on audit_events: alteration/deletion succeeds. |

### 7.4 Worker, lease, and duplicate-delivery tests

| ID | Invariant | Setup -> action | Expected assertion | Guard removal (paired run must fail) |
| --- | --- | --- | --- | --- |
| T-32 | I-11 | Two workers call acquire for the same invoice concurrently before expiry. | Exactly one gets a token; the other gets 409 `LEASE_BUSY`; one lease row; token starts at 1. | Drop the lease primary key or the expiry predicate: both acquire. |
| T-33 | I-12 | Worker A acquires token 1; lease expires; worker B acquires token 2; A calls `commit_worker_write` with token 1; B commits with token 2. | A gets 409 `LEASE_LOST`, no invoice/audit/outbox change; B commits and the version increments once. | Remove the token comparison: A writes after takeover. |
| T-34 | I-12 | Worker A acquires token 1; lease expires with no takeover; A calls commit. | 409 `LEASE_LOST`; no write. | Check token presence only, not expiry: A writes after expiry. |
| T-35 | I-12 | Pause A after it reads the lease but before it calls commit; B takes over token 2; resume A. Second variant: pause A inside the commit transaction after the lease check while B tries to acquire. | First variant: A's stale token is rejected. Second: B blocks on the row lock; A's `statement_timeout` (remaining lease minus margin) aborts before it can commit after expiry; no write. | Use an application-level check followed by an unconditional SQL update: stale A writes. |
| T-36 | I-05, I-12 | As the worker DB role, run `UPDATE invoices ...`, `INSERT INTO audit_events ...`, and `INSERT INTO outbox ...` directly. | All are denied by privileges; only `commit_worker_write`/`acquire_invoice_lease` execute; no change. | Grant direct update/insert to the worker role: bypass succeeds. |
| T-37 | I-13 | Deliver the same outbox event twice, sequentially and concurrently; replay the same job. | One `processed_worker_events` row; one side effect; second delivery returns the recorded result/no-op; no duplicate external call. | Drop the processed-event primary key: two side effects occur. |

### 7.5 Secret-rotation and leakage tests

| ID | Invariant | Setup -> action | Expected assertion | Guard removal (paired run must fail) |
| --- | --- | --- | --- | --- |
| T-38 | I-14 | Start two service replicas with key A; publish key B in the fake secret store; do not restart; issue new sessions/requests. | Within 60 s both replicas use B for new signatures; B-authenticated requests succeed; each replica reports the new keyring version; no process restart in logs. Old A remains accepted only in overlap. | Load the keyring only at boot: B is not used and B-authenticated requests fail; test fails. |
| T-39 | I-15 | Verify an old key at `retire_at - 1s`, at `retire_at`, and at `retire_at + 1s`; rotate a tenant API key and test before/after its `retire_at`. | Before deadline accepted; at/after deadline rejected with 401 `CREDENTIAL_EXPIRED` or verification failure; no fallback. | Ignore `retire_at`: old key is accepted indefinitely. |
| T-40 | I-16 | Stop the secret store after a good load; make auth/sign requests before and after `max_staleness`; try a request signed with an old key and with a made-up key. | Before staleness: last known good works; after: 503 `KEYRING_STALE`; made-up key rejected; no env/default key accepted; outbound signing refuses. | Fall back to a static env/default key: request succeeds after store loss. |
| T-41 | I-17 | Put a canary secret in the test secret store; trigger auth failure, validation failure, 500, and a log-heavy path; inspect logs, responses, audit events, traces, metrics, and build artifact. | Canary never appears; error body has only code/message/request_id; CI secret scan catches a canary committed to a fixture or artifact. | Log the raw Authorization header or secret: canary appears and test fails. |
| T-42 | I-16 | Publish malformed keyrings: duplicate kid, missing material, expired `current_kid`, `retire_at <= not_before`, unknown algorithm. | Refresh is rejected; last known good stays active; alert emitted; process does not crash; malformed key is never used. | Accept unvalidated keyring: malformed key becomes active. |

### 7.6 Domain, configuration, and error-contract tests

| ID | Invariant | Setup -> action | Expected assertion | Guard removal (paired run must fail) |
| --- | --- | --- | --- | --- |
| T-43 | I-18 | Create/update an invoice whose total does not equal lines + tax, or whose line currency differs; concurrently add a line and update the total in separate transactions. | 422/constraint abort; no inconsistent commit; concurrent transactions either serialize to a consistent state or one aborts. | Drop the deferred trigger/check: inconsistent total commits. |
| T-44 | I-19 | Start with `idempotency_retention < max_client_retry_window`, `lease_ttl <= worker_commit_timeout`, `keyring_max_staleness <= refresh_interval`, missing secret-store identity, and each bypass flag. | Process exits nonzero before serving; deployment fails; no partial startup. | Accept the bad config: service starts and later violates I-06/I-12/I-16. |
| T-45 | I-03, I-09, I-17 | Force an internal DB error and an unknown-action error on read and write endpoints; inspect status/body. | 5xx `INTERNAL_ERROR` or 403, not `200` with empty data; no stack trace, SQL, token, or other tenant id; `DBΔ=0`. | Catch all errors and return `200 []`: test fails. |

---

## 8. Guard-removal matrix

Run this matrix as part of the invariant test job. A green suite without these mutation runs is not evidence. Each removal is applied to a disposable branch/environment, the named test is run, and the test must fail (or the static check must report).

| Invariant | Guard to remove or replace with a no-op | Test that must fail |
| --- | --- | --- |
| I-01 | Drop/disable the RLS policy or remove the repository tenant predicate. | T-01, T-02, T-05, T-06 |
| I-02 | Drop the composite FK or the tenant-immutability trigger. | T-07 |
| I-03 | Replace `authorize_invoice_action()` with `return allow`, or ignore the action permission. | T-08, T-09 |
| I-04 | Treat the admin role as sufficient, or ignore grant tenant/action/time/actor. | T-11, T-12, T-14 |
| I-05 | Add a raw repository/SQL path or accept a bypass flag. | T-17, T-36 |
| I-06 | Drop `UNIQUE (tenant_id, creation_idempotency_key)` or the replay comparison. | T-18, T-19, T-25 |
| I-07 | Skip the principal/operation/hash comparison. | T-20, T-21, T-22 |
| I-08 | Remove the version predicate from the update. | T-26, T-27 |
| I-09 | Commit the invoice before validation/audit/outbox, or ignore audit/outbox failures. | T-28, T-29, T-30 |
| I-10 | Grant `UPDATE`/`DELETE` on `audit_events`, or remove the append-only trigger. | T-31 |
| I-11 | Drop the lease primary key or the expiry predicate. | T-32 |
| I-12 | Remove the token/expiry check, or grant direct invoice `UPDATE` to workers. | T-33, T-34, T-35, T-36 |
| I-13 | Drop the processed-event primary key. | T-37 |
| I-14 | Load the keyring only at boot. | T-38 |
| I-15 | Ignore `retire_at`. | T-39 |
| I-16 | Fall back to a static/default key after store loss or replace validation with `accept`. | T-40, T-42 |
| I-17 | Log the raw Authorization header or serialize the secret wrapper without redaction. | T-41 |
| I-18 | Drop the totals/currency constraint or trigger. | T-43 |
| I-19 | Remove startup validation. | T-44 |

Additional whole-system mutation checks:

- Replace `commit_worker_write()` with a plain `UPDATE` and run T-33..T-36; at least one must fail.
- Replace the admin grant function with `SELECT 1` and run T-11..T-16; at least one must fail.
- Remove RLS and the repository tenant predicate together; T-01 must expose B data. If the test still passes, the test is not actually exercising the tenant boundary.
- Replace the keyring refresh with a boot-time constant and run T-38; if T-38 still passes, the test never rotated the key.

---

## 9. Residual risk, operational requirements, and non-goals

### 9.1 Residual risk

| Risk | Why it remains | Required treatment |
| --- | --- | --- |
| Client retries with a new key | The server cannot know two differently keyed requests are the same logical operation. | API contract: retries must reuse the key; SDK defaults to reuse; document. |
| Hard deletion of invoices | The durable creation-key guard disappears with the row. | Soft delete or a creation-key tombstone; if hard delete is introduced, add a new invariant and test. |
| RLS policy drift / new tenant tables | A new table can be created without a policy. | CI schema test: every table with `tenant_id` has `ENABLE`/`FORCE RLS` and a matching policy; migration review. |
| Hash-chain or WORM audit gaps | Database append-only does not prevent a superuser/operator from altering storage. | Runtime roles are not owners; audit export to WORM; operator access is separately audited. |
| In-flight request across grant expiry/revocation | The transaction may complete after the wall-clock deadline. | Bound the transaction by the remaining grant validity; define revocation as effective for transactions that begin after it commits. |
| Secret-store outage | Fail-closed stops authentication after `max_staleness`. | Availability tradeoff accepted; monitor and alert; no static fallback. |
| Key compromise | Rotation limits exposure but cannot undo prior signatures. | Revoke/retire immediately, invalidate sessions, rotate dependent credentials; incident response out of scope. |
| Memory copies of secrets | Managed runtimes can copy buffers and crash dumps. | Best-effort zeroization; disable core dumps for secret-bearing processes; access control. |
| Clock skew | Lease and grant windows are time-based. | Use database time for leases/grants; NTP; document a small skew tolerance for secret timestamps. |
| Malicious internal code with DB credentials | Application code can set `app.tenant_id` arbitrarily. | Role separation, code review, RLS defense in depth, and least privilege. The threat model protects against API callers, not arbitrary code execution in the service. |
| Outbox consumer's downstream side effect | At-least-once delivery can repeat a call. | I-13 stable idempotency key; downstream must honor it. |
| Migrations/restores dropping constraints | A migration can silently remove a guard. | Run T-01..T-45 against the migrated schema and a restored snapshot; block release if any test fails. |

### 9.2 Operational requirements

- Database: PostgreSQL 15/16, one primary writer, `clock_timestamp()` used for lease/grant/audit decisions. A different database requires an equivalent RLS/constraint/locking design and a new test run; this document's evidence does not transfer.
- Roles: `app_rw` (non-owner, no `BYPASSRLS`), `app_worker` (execute-only on worker functions), `migrator` (migrations/backfills only, not runtime), `operator` (break-glass, separately gated/audited). No role other than `migrator`/`operator` may alter schema or bypass RLS.
- Monitoring: alert on `LEASE_LOST`, `VERSION_CONFLICT` spikes, `ADMIN_GRANT_REQUIRED`, `AUTHORIZATION_UNAVAILABLE`, `AUDIT_UNAVAILABLE`, `OUTBOX_UNAVAILABLE`, `KEYRING_STALE`, and keyring refresh failures. These are security/integrity signals, not only availability metrics.
- Backup/restore: a restore drill must include T-01, T-06, T-18, T-33, and T-39 on the restored snapshot. A backup that has never been restored is not evidence.
- Supply chain: dependencies and build inputs pinned; lockfile committed; SBOM/provenance for release artifacts; secret scanning and dependency checks in CI; no debug endpoint, default credential, or permissive CORS in release artifacts.
- Migration ordering: migrations are ordered, restartable, and preserve RLS, composite FKs, unique keys, and audit triggers. Negative tests run on migrated live-data fixtures, not only on an empty schema.

### 9.3 Non-goals

- Per-invoice ownership within a tenant (for example, "only the creator may edit"). If required, add a separate object-level predicate and tests; it must not replace the tenant boundary.
- Rate limiting, lockout, and abuse controls. They are important but do not substitute for authorization.
- Tax law compliance, invoice numbering rules, and accounting period rules.
- Multi-region active-active consistency. This design assumes a single primary for the invariants above.
- Grant issuance UX, approval workflow, and separation-of-duties policy. The API consumes grants; the grant service needs its own invariants.

---

## 10. Definition of done

- [ ] Every invariant I-01..I-19 has an owner, an enforcement point in the code/schema, and an entry in the invariant map.
- [ ] Every invariant has at least one negative test, and every negative test has a guard-removal run that fails.
- [ ] The test suite runs against the migrated schema and a restored snapshot, not only a fresh test database.
- [ ] T-17's architecture/static test covers every route in section 1.2 and fails on a new unlisted route.
- [ ] Concurrency tests use two connections/instances for T-19, T-26, T-32, T-33, T-35, and T-37.
- [ ] Secret rotation is exercised against the real deployment secret store in staging, without a process restart, on at least two replicas.
- [ ] Grant revocation, expiration, and self-grant rejection are tested against the real grant service contract.
- [ ] Residual risks in section 9.1 are recorded in the release note; any unmitigated item has an explicit owner and expiry.
- [ ] Logs, errors, audit events, traces, and build artifacts have been scanned for the canary secret in T-41.
- [ ] A restore drill and a post-migration negative-test run are recorded.




