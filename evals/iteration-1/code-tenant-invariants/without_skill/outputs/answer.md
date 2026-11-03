# Invariant Map: Multi-Tenant Invoice API

## 1. Scope and trust model

This map covers invoice creation and update through the public API, the authorization service, the database, background workers, and the secret/key management path.

Trust boundaries and assumptions:

- The only authoritative identity source is a verified credential (for example, a signed JWT or mTLS identity). A tenant identifier, role, or admin flag supplied in a path, header, query string, or request body is never authoritative.
- The database is a security boundary, not just a persistence detail. Application bugs must not be able to turn into cross-tenant reads or writes.
- Admin is a privileged role, not a tenant membership. Admin access to tenant data is denied by default and requires a separate, explicit, scoped grant.
- Workers are untrusted with respect to liveness. Any worker can pause, lose its lease, or resume after another worker has taken over.
- Secrets include token-signing keys, encryption keys, webhook HMAC keys, and database/API credentials. Rotation must not require a process restart.

Terms used below:

- **Effective tenant**: the tenant derived from the authenticated principal, never from caller-controlled input.
- **Grant**: a persisted record authorizing a specific admin, for specific tenants, specific actions, a specific time window, and a stated reason.
- **Fencing token**: a monotonically increasing value issued with a lease; writes carry it so storage can reject stale owners.
- **Idempotency record**: a persisted mapping from an idempotency key to the original request fingerprint and original response.

---

## 2. Invariant catalog

### 2.1 Tenant isolation invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **T1** | The effective tenant is derived only from the verified principal. If a tenant identifier also appears in the path, header, query, or body, it must exactly equal the effective tenant or the request is rejected. No implicit fallback to a caller-supplied value. | Authentication middleware plus request validation; repository takes tenant from an immutable request context. | Tenant spoofing by header/body manipulation. |
| **T2** | `invoice.tenant_id` is assigned at insert from the effective tenant and is immutable for the lifetime of the row. | Database trigger or generated/immutable column; `UPDATE` privilege excludes `tenant_id`; repository has no tenant-change method. | An invoice can be moved into another tenant, or a foreign invoice can be “adopted.” |
| **T3** | Every read, write, aggregate, export, search, and join touching invoices is tenant-scoped. Child rows (lines, attachments, events) inherit tenant scope and cannot be attached to a foreign invoice. | Composite tenant-aware foreign keys, repository scoping, and independently enforced row-level security (RLS). | IDOR, cross-tenant counts, cross-tenant joins, orphaned or mis-parented child data. |
| **T4** | Cross-tenant access is indistinguishable from “not found.” The response status, body shape, headers, and observable timing do not reveal whether the object exists in another tenant. | Uniform 404 path; no tenant-specific error text; constant-shape responses; timing review for lookup paths. | Existence oracle and invoice enumeration across tenants. |
| **T5** | Resource identifiers are not authorization. Knowing or guessing an invoice UUID grants nothing; every access is re-authorized against the effective tenant. | Authorization check on every operation; no “possession of ID” shortcuts; no signed-URL bypass of tenant checks. | IDOR via leaked identifiers. |
| **T6** | Tenant-scoped data is partitioned everywhere it leaves the primary database: cache keys, queue names/messages, object-storage keys, export files, logs, and search indexes. | Tenant prefix in cache keys and object paths; tenant field in queue messages; tenant filter in index queries; redaction. | Cross-tenant cache poisoning, export leakage, search-result leakage. |
| **T7** | Asynchronous work re-establishes tenant context from a trusted internal record and revalidates it. A worker never inherits an ambient tenant from a prior job or trusts a tenant field copied from an untrusted request. | Job payload carries tenant plus originating actor/grant; worker validates tenant against the referenced invoice; per-job context reset. | Cross-tenant writes by worker reuse or queue injection. |
| **T8** | Tenant identifiers are canonicalized and compared exactly. No case folding, Unicode normalization shortcuts, prefix matching, or trimming that could make two distinct tenants collide. | Canonical tenant ID format enforced at issuance; exact-match comparisons; unique index on canonical value. | Confusable-tenant attacks and accidental cross-tenant matches. |

### 2.2 Admin-grant invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **A1** | Default deny. Holding an `admin` role alone grants no tenant-data access. Every admin operation on tenant data requires an explicit, persisted grant. | Authorization service checks a grant record in addition to role; no “admin bypass” branch. | A compromised or over-broad admin role becomes universal tenant access. |
| **A2** | Grants are least-privilege and explicit: named grantee, exact tenant(s), exact actions, optional resource constraints, expiry, maximum uses, grantor, and reason/ticket reference. Wildcard tenants or wildcard actions are rejected unless a separately approved break-glass policy exists. | Grant schema with NOT NULL scope fields and validation; no defaults that broaden scope. | “Temporary” admin access silently becomes permanent global access. |
| **A3** | Grant validity is checked at execution time on the server, not at grant-issuance time and not only in the UI. Expiry, revocation, and use-count exhaustion take effect immediately; if the grant store is unavailable, the decision is deny. | Synchronous or bounded-staleness authorization check; fail-closed error handling; no long-lived authorization cache. | Revoked or expired admins continue to act. |
| **A4** | Separation of duties: an admin cannot issue a grant to themselves, cannot approve their own break-glass request, and cannot modify the scope of their own grant. Grant creation and grant use are distinct permissions. | Grantor != grantee constraint; independent approver for break-glass; immutable grant scope after issuance. | Self-escalation and unaudited privilege. |
| **A5** | Every admin action, including denied attempts, produces an append-only audit record containing actor, grant ID, tenant, target, action, before/after state, request ID, and timestamp. The audit write is part of the action’s success criteria. | Transactional audit/outbox write; append-only table permissions; tamper-evident log. | Admin actions cannot be reconstructed or attributed. |
| **A6** | An admin grant widens which tenants an admin may name; it never removes the requirement to scope each operation to exactly one tenant. Bulk operations must be explicitly tenant-scoped and must not silently span tenants. | Per-operation tenant parameter derived from the grant; bulk endpoints require explicit tenant list and produce per-tenant audit entries. | “Admin” becomes an unscoped superuser path around T3. |
| **A7** | Admin actions cannot change immutable tenant ownership, cannot impersonate a tenant user without a separate audited impersonation grant, and cannot alter audit records or grant history. | Privilege separation at the database layer; append-only audit; no `tenant_id` update path. | An admin can hide their tracks or permanently seize tenant data. |

### 2.3 Idempotency invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **I1** | Every invoice-creating request requires a client-generated idempotency key with sufficient entropy. The key scope is `(tenant_id, operation, key)`. Missing, empty, over-long, or malformed keys are rejected. | Request validation; key format/length limits; tenant from effective context. | Retries without a key create duplicates; weak keys collide. |
| **I2** | The idempotency record and the invoice insert are committed atomically in one transaction. A database uniqueness constraint, not an application-level check-then-insert, is the final arbiter under concurrency. | `PRIMARY KEY`/`UNIQUE` on `(tenant_id, operation, key)`; same transaction for invoice and record; unique-violation handling. | Two concurrent retries both pass the check and create two invoices. |
| **I3** | The idempotency record stores a canonical fingerprint of the request (method, route, tenant, relevant body fields). Same key plus same fingerprint returns the original stored response without re-executing side effects. Same key plus different fingerprint returns a conflict and performs no mutation. | Canonical request hashing; stored response status/body; explicit 409 path. | Key reuse silently applies a different invoice, or retries mutate twice. |
| **I4** | At most one invoice exists per `(tenant_id, operation, key)`. At-least-once delivery from clients or queues produces at-most-once invoice creation. | Same uniqueness constraint plus transactional outbox for downstream effects. | Duplicate invoices from retries, duplicate downstream events. |
| **I5** | Idempotency records are retained at least as long as the maximum client retry horizon and queue retry window, and the retention policy is explicit. Expired keys are treated as new requests or rejected according to a documented contract, never silently confused with old ones. | Retention job with a window greater than retry maximum; expiry visible in the API contract. | A retry after cleanup creates a duplicate. |
| **I6** | Updates use optimistic concurrency (`version`/`If-Match`) and/or their own idempotency keys. A stale writer cannot overwrite a newer state, and a retried update cannot apply twice. | Version column with conditional `UPDATE ... WHERE version = :expected`; update idempotency record. | Lost updates and duplicate state transitions. |
| **I7** | If invoice creation fails, the idempotency record is not left claiming success. If the response is lost after commit, retrying returns the stored committed response. | Single transaction; response persisted before commit; failure rolls back both rows. | “Phantom success” or retries that can never succeed. |

### 2.4 Lease and fencing invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **L1** | A worker may mutate invoice state only while it holds a valid lease for that work item. Each lease has a holder identity and a monotonically increasing fencing token. | Lease table with `holder`, `fencing_token`, `expires_at`; acquisition via atomic compare-and-swap. | Two workers act on the same invoice. |
| **L2** | Every write is conditional on the lease still being valid at commit time, and on the writer’s fencing token being the current one (or at least the highest seen for that resource). The check is inside the same database transaction as the mutation. | `UPDATE ... WHERE fencing_token = :token AND expires_at > now()`; or lock the lease row and recheck before commit. | A worker checks the lease, pauses, loses it, then commits anyway. |
| **L3** | Lease acquisition is atomic and fencing tokens strictly increase. No two workers can hold the same token, and a token is never reused for a new lease of the same resource. | Database sequence or `UPDATE ... SET token = token + 1 ... RETURNING`; unique current-holder constraint. | ABA problem: an old holder’s write is accepted as current. |
| **L4** | All externally visible side effects (events, emails, webhooks, downstream API calls) are written to a transactional outbox in the same transaction as the state change, and are emitted only after commit by an owner that is still valid. Consumers deduplicate by event ID. | Outbox table; relay with fencing/ownership check; consumer idempotency. | Stale worker sends an email or emits an event for a mutation that never committed. |
| **L5** | A worker that loses its lease must not rely on cached reads or previously computed decisions. On retry it re-reads current state and obtains a new token; any commit attempt with the old token aborts atomically. | No long-lived in-memory state across lease boundaries; transaction restart on fencing failure. | Stale decisions overwrite newer state. |
| **L6** | Lease validity is evaluated against a single trusted clock (database/server time), not worker wall-clock time. Clock skew and paused processes cannot extend a lease. | `now()` from the database; bounded clock-skew assumptions; no lease extension based on client time. | A paused or skewed worker believes it still owns the lease. |

### 2.5 Secret-rotation invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **S1** | Every secret is versioned and has a key ID (`kid`). Tokens, signatures, and encrypted envelopes carry the `kid` needed to select the correct key. | Keyring with `kid`; `kid` in token header or ciphertext envelope. | Rotation becomes a flag day; old and new keys cannot coexist. |
| **S2** | Signing uses exactly one active key at a time. Verification accepts the active key and all not-yet-retired keys. | Keyring state machine: `pending -> active -> verify-only -> retired`. | New tokens fail verification during rotation, or retired keys remain trusted forever. |
| **S3** | Rotation is hot: the process observes new key material from the secret store or watched file, atomically swaps the in-memory keyring, and starts signing with the new active key within a bounded refresh interval, without a restart. | Secret-manager watch or bounded polling; atomic keyring swap; no key material read only at process startup. | Rotation requires a restart or leaves instances inconsistent. |
| **S4** | Old keys remain verify-only for at least the maximum token lifetime plus clock skew, then are retired. Retirement is explicit, audited, and irreversible. | Overlap window policy; `kid` retention; retirement job and audit. | Rotation invalidates live sessions, or compromised keys remain valid indefinitely. |
| **S5** | A compromised key can be emergency-revoked immediately, independent of the normal rotation schedule. Revocation is checked before or alongside cryptographic verification, and other keys are unaffected. | Deny list / emergency keyring update; tests for immediate effect. | A known-compromised key keeps minting or validating credentials. |
| **S6** | An instance that cannot refresh the keyring within the allowed staleness bound stops signing (fail closed) rather than continuing with a retired or unknown key. Verification behavior for unavailability is explicitly defined and tested; high-value paths fail closed. | Staleness deadline; health/readiness transition; error handling. | An isolated instance signs with an outdated key or accepts a revoked key. |
| **S7** | Secrets are never logged, returned in errors, embedded in invoice records, or exposed through debug endpoints. Key material exists only in memory and the secret store. | Structured logging redaction; error sanitization; secret scanning in CI. | Rotation is defeated by leaked credentials. |

### 2.6 State and audit invariants

| ID | Invariant | Primary enforcement | Consequence if violated |
|---|---|---|---|
| **C1** | Invoice state transitions follow an explicit state machine (for example `draft -> issued -> paid -> void`). Invalid transitions are rejected, and concurrent transitions are serialized or rejected by version checks. | Transition table/guard; optimistic concurrency; database constraint where practical. | Double payment, void-after-pay, or contradictory status. |
| **C2** | Every mutation is attributable: request ID, actor, effective tenant, admin grant ID (if any), idempotency key (if any), and timestamp are recorded. | Mutation audit/outbox record in the same transaction. | Fraud and operational incidents cannot be reconstructed. |
| **C3** | Audit records are append-only and tamper-evident. Application roles cannot update or delete them. | Separate audit role/table permissions; hash chaining or WORM storage. | An attacker or rogue admin erases evidence. |

---

## 3. Negative tests that make the invariants credible

A test only counts as evidence if it asserts the **database state** and **absence of side effects**, not merely an HTTP status. Each test below should be written so that removing the corresponding enforcement makes it fail.

### 3.1 Tenant-isolation tests

| Test | Attack or fault | Expected result | Oracle |
|---|---|---|---|
| **NT-T1** | Authenticate as tenant A; send `X-Tenant-Id: B`, `tenant_id: B` in body, and `?tenant=B`. | Request rejected (400/403) or the supplied values are ignored; no invoice is created for either tenant. | Response contains no B data; DB has no row with `tenant_id = B` from this request. |
| **NT-T2** | Forge or tamper with the token’s tenant claim, or present an unsigned/incorrectly signed token. | 401; no data access. | Auth middleware rejects before repository is called; no DB query for the forged tenant. |
| **NT-T3** | Tenant A requests tenant B’s invoice by UUID on read, update, delete, and child-resource endpoints. | Identical 404 to a random nonexistent UUID; B’s row unchanged. | Status, body schema, headers, and error code match the nonexistent case; B row hash unchanged. |
| **NT-T4** | Tenant A lists invoices with filters, sorting, pagination, search, and count/aggregate endpoints, including a filter for a known B invoice number. | Only A rows returned; count reflects A only; B filter yields empty result. | Compare against direct A-only DB query; no B identifier appears in any page or total. |
| **NT-T5** | Tenant A posts a child row (invoice line, attachment, note) referencing B’s invoice ID. | Rejected; no child row created. | Database rejects the composite foreign key; B invoice unchanged. |
| **NT-T6** | Use the application’s raw DB role with session tenant A to `SELECT`, `UPDATE`, and `INSERT` invoices for B. | RLS returns zero rows or raises an error; no B mutation. | Direct SQL assertions with the app role, not an admin role. |
| **NT-T7** | Two tenants use the same idempotency key string. | Each gets its own invoice; neither can read the other’s result. | Two distinct invoice IDs, each with the correct tenant; no cross-tenant response replay. |
| **NT-T8** | Seed tenant A and tenant B caches, exports, and search indexes; access through A. | No B data is returned from cache, export download, or search. | Object paths and cache keys include tenant; byte-level scan for B’s invoice number in A’s export. |
| **NT-T9** | Compare response timing and error text for “B’s real invoice” versus “random UUID.” | Statistically indistinguishable within the test’s tolerance; same status and body shape. | Repeated samples; no tenant-specific error strings in logs returned to the client. |
| **NT-T10** | Use tenant IDs that differ only by case, whitespace, Unicode normalization, or a shared prefix. | Treated as distinct or rejected by canonicalization; never matched to the wrong tenant. | Exact-match DB lookups; no row from the other tenant. |
| **NT-T11** | Inject a queue message or job payload with tenant B while the worker’s previous job was tenant A. | Worker rejects or processes only under the trusted job tenant; no A context leakage into B or vice versa. | Worker logs show fresh tenant context; DB writes carry the correct tenant. |
| **NT-T12** | Attempt an unscoped raw query or repository call that omits the tenant predicate. | Static analysis/test fails; at runtime RLS blocks it. | Query plan or test harness proves the tenant predicate is present; an integration test with RLS enabled returns zero cross-tenant rows. |

### 3.2 Admin-grant tests

| Test | Attack or fault | Expected result | Oracle |
|---|---|---|---|
| **NA-A1** | Admin token with no grant reads or updates a tenant invoice. | 403; no data returned or changed; denial audited. | Audit record includes actor, tenant, action, “denied: no grant.” |
| **NA-A2** | Grant is for tenant A; admin targets tenant B. | 403/404; no B data; denial audited. | B row unchanged; audit names the requested tenant and grant ID. |
| **NA-A3** | Grant allows `invoice:read`; admin attempts `invoice:update`. | 403; no mutation. | Grant action set checked exactly; no wildcard expansion. |
| **NA-A4** | Grant expired one second ago. | 403 immediately; no grace period. | Authorization check uses server time; audit records expiry. |
| **NA-A5** | Grant revoked; admin retries immediately on every replica. | 403 on the next request; no cached allow. | Test across all replicas; revocation propagation bounded by the documented TTL, ideally zero. |
| **NA-A6** | Grant has `max_uses = 1`; admin uses it twice concurrently. | Exactly one success; second denied. | Use counter updated atomically; DB row count and audit count match. |
| **NA-A7** | Admin attempts to create a grant for themselves, approve their own request, or widen their own grant. | Rejected by separation-of-duties rule. | No grant row created or modified; audit records the attempt. |
| **NA-A8** | Grant service is unavailable, times out, or returns malformed data. | Request denied (fail closed), not allowed. | No invoice mutation; error is 503/403, never 200. |
| **NA-A9** | Admin successfully updates an invoice; then attempt to update/delete the audit record through the app role. | Audit record exists with before/after and grant ID; tampering is denied. | Direct DB assertion; append-only permissions enforced. |
| **NA-A10** | Client supplies `role: admin` in a header, body, or unsigned claim. | Ignored; authorization uses server-side role and grant only. | No privilege change; request treated as ordinary user. |
| **NA-A11** | Admin with a valid grant attempts to change `invoice.tenant_id` or move an invoice to another tenant. | Rejected; tenant remains immutable. | DB trigger/privilege blocks it; row hash unchanged except permitted fields. |
| **NA-A12** | Admin bulk request mixes tenant A and tenant B IDs without an explicit multi-tenant grant. | Entire request rejected, or only explicitly authorized tenants processed with per-tenant audit; no silent cross-tenant success. | Per-tenant result and audit rows; no partial unscoped write. |
| **NA-A13** | Admin attempts to act on tenant data after grant expiry but before the next cache refresh. | Denied at execution time. | Authorization store is authoritative; no long-lived allow cache. |

### 3.3 Idempotency tests

| Test | Attack or fault | Expected result | Oracle |
|---|---|---|---|
| **NI-I1** | Create invoice with no idempotency key, empty key, whitespace-only key, or over-limit key. | 400; no invoice. | DB count unchanged. |
| **NI-I2** | Fire N identical create requests concurrently behind a barrier with the same key. | Exactly one invoice; all successful responses return the same invoice ID and body. | `SELECT count(*)` is 1; all response IDs equal; exactly one outbox event. |
| **NI-I3** | Commit succeeds but the client never receives the response; client retries with the same key and payload. | Returns the original stored response; no second invoice and no second side effect. | Invoice count 1; outbox count 1; response matches original status/body. |
| **NI-I4** | Same key, different amount, currency, customer, or line items. | 409 conflict; original invoice unchanged; no new invoice. | Fingerprint mismatch detected; DB row hash unchanged; audit records conflict. |
| **NI-I5** | Same key used for a different operation or endpoint (create versus update, or different resource type). | 409 or 400; no mutation. | Key scope includes operation and route; invoice count unchanged. |
| **NI-I6** | Tenant A and tenant B use the same key string concurrently. | Two separate invoices, one per tenant; no cross-tenant replay. | Each response’s invoice belongs to the caller’s tenant; no B data in A’s response. |
| **NI-I7** | A 100-request retry storm with mixed timing and duplicate delivery. | Exactly one invoice; all retries converge on the same result or receive a well-defined in-progress response. | DB count 1; no orphan idempotency rows; outbox count 1. |
| **NI-I8** | Retry after the documented retention window. | Behavior matches the contract (new invoice or explicit rejection); never a silent duplicate within the retry window. | Boundary test at retention minus one second and plus one second. |
| **NI-I9** | Concurrent updates with the same version / `If-Match`, or the same update idempotency key. | One succeeds; the other gets 409/412; final state reflects exactly one transition. | Version increments once; audit shows one applied update. |
| **NI-I10** | Invoice insert fails (constraint, DB error) after idempotency record insert, or vice versa. | Both roll back; retry can succeed cleanly. | No idempotency row claiming success without an invoice; no invoice without a matching record. |
| **NI-I11** | Keys differing only by case, whitespace, or Unicode normalization. | Treated as distinct or rejected by canonicalization; no accidental collision. | Exact-match unique constraint; no cross-request replay. |

### 3.4 Lease and fencing tests

| Test | Attack or fault | Expected result | Oracle |
|---|---|---|---|
| **NL-L1** | Worker A acquires a lease, is paused past expiry, worker B acquires the lease and completes, then A resumes and attempts to commit. | A’s commit is rejected with a stale-fence error; B’s result remains; A cannot overwrite. | Final row equals B’s write; A’s transaction rolled back; no A-originated outbox event. |
| **NL-L2** | Two workers acquire the same work item simultaneously. | Exactly one lease succeeds; the loser cannot write with the old token. | Lease table has one current holder; fencing tokens strictly increase; one final state. |
| **NL-L3** | Commit attempt at `expires_at - 1ms`, `expires_at`, and `expires_at + 1ms` using database time. | Accepted only before expiry; rejected at/after expiry. | Boundary assertions with a controlled DB clock; no worker-clock influence. |
| **NL-L4** | Stale worker attempts to write an outbox event, send an email, or call a webhook after lease loss. | No externally visible effect from the stale worker; the valid worker emits exactly one event. | Outbox count 1; email/webhook mock call count 1; event carries valid fencing token/owner. |
| **NL-L5** | Worker crashes after the invoice update but before commit, or after commit but before acknowledgment. | Before commit: full rollback, retry completes once. After commit: retry sees the committed result, no duplicate. | No partial rows; invoice and outbox atomic; retry converges. |
| **NL-L6** | Set worker wall-clock forward or backward by minutes; pause the process. | Lease validity unchanged because it is evaluated against server/DB time. | Commits accepted/rejected by DB time only. |
| **NL-L7** | Replay an old fencing token after a newer token has been issued. | Rejected; token cannot be reused for a new lease. | Fencing token monotonic; old-token update affects zero rows. |
| **NL-L8** | New worker acquires the lease while the old worker holds a database row lock / open transaction. | The new owner either waits or the old transaction aborts; the old owner can never commit after losing the lease. | Serialization outcome is one of the two valid outcomes; no double commit. |
| **NL-L9** | Retry the same job after a lease handoff. | Exactly-once effect via idempotency/fencing; no duplicate invoice or duplicate event. | DB row count 1; outbox dedupe key enforced. |
| **NL-L10** | Worker reads invoice state, loses lease, then writes based on stale read. | Write rejected by fence; retry re-reads current state. | Final state reflects the newest valid writer; no lost update. |

### 3.5 Secret-rotation tests

| Test | Method | Expected result | Oracle |
|---|---|---|---|
| **NS-S1** | Issue a token, rotate the signing key, then verify the old token and issue a new one. | Old token still verifies during overlap; new token carries the new `kid`. | Token header `kid` matches active key; verification succeeds for both non-retired keys. |
| **NS-S2** | Rotate via secret store while the process is running. | New signatures use the new key within the bounded refresh interval; process PID/start time unchanged. | PID unchanged; response token `kid` changes; no restart in logs. |
| **NS-S3** | Keep an old key past its overlap window, then attempt verification. | Old tokens rejected after retirement; no indefinite trust. | Verification uses only active/verify-only keys; retired `kid` returns 401. |
| **NS-S4** | Retire a key early, before the maximum token lifetime. | Rotation policy prevents it or live tokens fail predictably; test asserts the configured guard. | Retire operation rejected while live tokens could exist. |
| **NS-S5** | Emergency-revoke a compromised key. | Tokens signed by that key are rejected immediately; tokens signed by other keys still work. | Deny list checked before acceptance; no restart required. |
| **NS-S6** | Present a token with unknown `kid`, malformed `kid`, or an algorithm-confusion attempt (for example `alg: none`, HMAC versus RSA confusion). | 401; no fallback to a default key or algorithm. | Verification rejects unknown `kid` and disallowed algorithms; no crash. |
| **NS-S7** | Make the secret store unavailable during signing and during verification. | Signing fails closed; verification behavior matches the documented policy (fail closed for high-value paths). | No token minted with stale/retired key; health/readiness reflects degraded state. |
| **NS-S8** | Scan logs, error responses, traces, and exception messages after a forced key error. | No key material, secret value, or private key appears. | Automated secret scanning over captured output. |
| **NS-S9** | Rotate while a replica is partitioned from the secret store. | The replica stops signing after the staleness bound; it does not use the retired key. | Replica health/readiness false; no new tokens with old `kid` after deadline. |
| **NS-S10** | Rotate under concurrent load. | No request fails because the keyring was partially swapped; keyring swap is atomic. | Error rate unchanged; every issued token verifies; old and new keys coexist correctly. |
| **NS-S11** | For encryption-at-rest: decrypt old ciphertext after rotation and encrypt new data. | Old ciphertext decrypts with its `kid`; new ciphertext uses the new key. | Envelope `kid` assertions; no re-encryption flag day required. |
| **NS-S12** | Attempt to reintroduce a retired key. | Rejected by key-state machine; retirement is irreversible. | Keyring rejects transition from retired to active; audit records the attempt. |

### 3.6 State and audit tests

| Test | Fault | Expected result | Oracle |
|---|---|---|---|
| **NC-C1** | Attempt an invalid transition (for example pay a voided invoice) and two conflicting transitions concurrently. | Invalid transition rejected; concurrent conflict resolved by version check; one winner. | Final state valid; audit shows one applied transition and one rejection. |
| **NC-C2** | Perform a mutation and inspect the audit/outbox record. | Record contains actor, tenant, grant ID when applicable, idempotency key, request ID, before/after, timestamp. | Field-level assertions; correlation ID matches the request. |
| **NC-C3** | Attempt to update or delete an audit record with the application role; attempt to truncate the audit table. | Denied. | DB permission error; audit row count unchanged. |

---

## 4. Enforcement blueprint (defense in depth)

The invariants above should not rely on a single layer. A practical design:

1. **Authentication middleware** verifies the credential and produces an immutable context object: `principal_id`, `effective_tenant`, `roles`, and `request_id`. It rejects tenant identifiers that disagree with the credential.
2. **Authorization middleware** evaluates grant records for admin operations using a fail-closed check. It does not trust client-supplied roles or tenant scope.
3. **Repository layer** requires an explicit tenant argument on every invoice operation. There is no “default tenant,” no optional tenant filter, and no raw query escape hatch in application code.
4. **Database constraints** provide the real backstop:
   - `invoices(id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, ..., version BIGINT NOT NULL)`
   - `UNIQUE (tenant_id, id)` and tenant-aware foreign keys for child tables.
   - A trigger or privilege rule that rejects any `UPDATE` changing `tenant_id`.
   - Row-level security policy on every tenant-owned table: `USING (tenant_id = current_setting('app.tenant_id', true))`, with the setting established per transaction from the verified context.
   - `idempotency(tenant_id, operation, key, request_hash, response_status, response_body, invoice_id, created_at, PRIMARY KEY (tenant_id, operation, key))`.
   - `admin_grants(id, grantee, tenant_id, actions, expires_at, max_uses, uses, revoked_at, grantor, reason, created_at)` with `grantor <> grantee` and immutable scope.
   - `leases(resource_id PRIMARY KEY, holder, fencing_token BIGINT NOT NULL, expires_at)` with atomic token increment.
   - `outbox(event_id PRIMARY KEY, tenant_id, aggregate_id, fencing_token, payload, created_at)`.
5. **Worker layer** acquires leases atomically, carries the fencing token into every write predicate, writes state plus outbox in one transaction, and aborts on a zero-row fence update.
6. **Keyring** is loaded from a watched secret store, swapped atomically, and modeled as a state machine: `pending -> active -> verify-only -> retired`. Signing selects only `active`; verification accepts `active` and `verify-only`; revocation is an immediate deny.
7. **Audit pipeline** is append-only, correlated by request ID, and receives both successful and denied admin attempts.

## 5. How to make the tests credible

- **Assert state, not just status codes.** Every negative test must check the target row, tenant ownership, version, outbox count, and side-effect mock calls.
- **Use deterministic time and real concurrency.** Control the database clock for lease-expiry boundaries; use barriers and repeated runs for idempotency and lease races.
- **Inject faults.** Pause/resume workers, drop responses after commit, partition the secret store, revoke grants mid-request, and fail the audit write.
- **Run tests against production-like enforcement.** RLS and DB constraints must be enabled in the test database; bypassing them invalidates the evidence.
- **Mutation-test the invariants.** Disable each enforcement (remove RLS, drop the unique constraint, remove the fencing predicate, remove the grant check) and confirm at least one negative test fails. An invariant with no failing mutant is not covered.
- **Property-based coverage.** Generate random tenant pairs and resource IDs for IDOR, random retry schedules for idempotency, random pause points for leases, and random rotation timings for the keyring.
- **Keep security regressions in CI.** Treat cross-tenant access, duplicate invoices, stale-fence commits, and use of retired keys as release-blocking failures.

## 6. Threat-to-invariant quick map

| Threat | Invariants that stop it |
|---|---|
| IDOR / cross-tenant object access | T1–T5, T8 |
| Tenant spoofing via header/body/path | T1, T8 |
| Admin privilege abuse or stale access | A1–A7 |
| Duplicate invoices from retries | I1–I7 |
| Duplicate downstream events or emails | I4, L4, L9 |
| Zombie worker committing after lease loss | L1–L6 |
| Lost update / double state transition | I6, C1, L2, L5 |
| Key compromise or botched rotation | S1–S7 |
| Repudiation of admin actions | A5, A7, C2, C3 |
| Existence oracle across tenants | T4, T9-equivalent test |
