# Review: cross-tenant invoice negative suite

**Verdict.** The suite is green but does not support "tenant isolation is covered." With the permission service stubbed to deny, it proves that an injected deny yields 404/403 on two routes and a session-less PATCH yields 401. It does not exercise the real authorization decision, verify query scoping, show that a refused write left the invoice untouched, or establish which layer refused.

## What the three tests establish

| Test | Proves | Does not prove |
| --- | --- | --- |
| 1. B GETs A-id, expects 404 | The GET route does not return 200 under an injected deny | That A-id exists; that the query is tenant-scoped; that 404 came from authorization rather than a missing fixture or blanket 404 |
| 2. B PATCHes A-id, expects 403 | The PATCH route honors a deny before returning success | That the real policy denies; that B's principal had permission in its own tenant (403 may be role denial); that no UPDATE ran; that no event/webhook/audit was emitted |
| 3. Role-less session PATCHes A-id, expects 401 | A request without a valid session is rejected on one route | Tenant isolation or role authorization; correct 401-versus-403 semantics for an authenticated but role-less user |

Test 2 is the weakest. "Tenant B" is not a role. A B member or viewer receives 403 from the role check before the tenant predicate is evaluated; a policy that ignores tenant entirely still passes. The decisive case is a **tenant B owner/admin** with write permission inside B, attempting to write A's invoice.

Test 1 may pass for the wrong reason. The suite never asserts that A-id exists and is readable by A; a typo, a soft-deleted fixture, or premature cleanup also produces 404.

Test 3 is orthogonal: it tests the auth gate on one method and conflates unauthenticated (401) with authenticated but role-less (normally 403).

## Why the oracle is weak

1. **The mock replaces the mechanism under test.** The claim concerns the real permission service and data path. With it mocked to deny, the test verifies stub-to-response wiring, not policy; a production "allow all" policy would not fail.
2. **Status codes are not refusal classification.** An application 403, a proxy 404, and a platform block are different claims. Assert the application error code, reason, and originating layer.
3. **No world-state assertion.** A handler that performs the UPDATE and then returns 403 passes Test 2. Denial must precede any write, and the database must be compared before and after.
4. **No positive controls.** A service returning 404/403/401 for everyone, including tenant A reading its own invoice, passes all three. A's successful GET and PATCH are required to show the routes work.
5. **The expected statuses leak existence.** A foreign invoice returns 404 on GET but 403 on PATCH. If absent IDs return 404 on both, the 403 confirms A's invoice exists. Map cross-tenant access uniformly to 404; reserve 403 for same-tenant role failures.
6. **The fixture is unverified.** Isolation tests are only as good as the tenants, roles, and rows created. Assert the fixture through a privileged read first.

## Claim map

**P** = proven by a live test, **W** = attempted but oracle insufficient, **U** = uncovered. The current suite has no **P** rows.

| ID | Claim | Mechanism | Required negative | Status |
| --- | --- | --- | --- | --- |
| C1 | Cross-tenant reads return no A data | Tenant-scoped query plus object policy | B all roles GET A-id; uniform 404; no A fields; absent-ID control | **W** (Test 1: mock, status only) |
| C2 | Cross-tenant writes cannot modify A's invoice | Policy plus tenant-scoped UPDATE; RLS if present | B admin PATCH A-id; row, version, related rows unchanged | **W** (Test 2: mock, no state check) |
| C3 | Cross-tenant access does not reveal existence | Uniform 404, generic body and headers | Foreign versus absent ID on every method | **U** (PATCH 403 leaks) |
| C4 | Invoice endpoints require authentication | Auth middleware on the route family | Every method with missing/expired/revoked token; 401 + `WWW-Authenticate` | **W** (Test 3: one route) |
| C5 | Role authorization is correct inside a tenant | Policy engine role/action matrix | Viewer read 200/write 403; editor write 200; role-less 403 | **U** (mock always denies) |
| C6 | Tenant identity comes from session, not client input | Server-derived tenant claim; ignore body/query/header tenant | PATCH own invoice with `tenant_id: A`; POST with `tenant_id: A`; token-claim confusion | **U** |
| C7 | Every path enforces tenancy | Shared middleware, handler check, repository scope | List, subresources, bulk, export, reports, alternate APIs, all methods | **U** |
| C8 | Denied requests have no side effects | Authorization before transaction; rollback; no outbox | Snapshot invoice/related tables and event queues before and after | **U** |
| C9 | Permission service decides and is called correctly | Real policy tests plus argument spy | Role × tenant × action matrix; spy asserts subject, action, resource tenant | **U** (mock; args unasserted) |
| C10 | Refusals come from our authorization layer with a stable code | Error taxonomy and layer marker | Error code/reason assertions; mutate the guard and confirm failure | **U** |
| C11 | Data layer stays scoped even if policy allows | Repository tenant predicate/RLS | Cross-tenant repository call; forged allow still fails or names sole layer | **U** |
| C12 | Cross-tenant attempts are audited; audit is immutable | Security event pipeline | One denial event with actor, tenant, target, decision; tenant cannot edit it | **U** |

## Missing negative tests

**Fixtures and controls**

- **N1 `fixture_and_positive_controls`.** Assert A-id exists and belongs to A via a privileged read. A owner/admin GETs it (200, expected fields); A editor PATCHes it (200, version increments). Otherwise the negatives are vacuous.
- **N2 `absent_id_semantics`.** GET and PATCH an ID that exists nowhere, as A and B. Establish baseline status and body per method; use it to interpret Test 1 versus Test 2 and detect leakage.

**Real enforcement path**

- **N3 `policy_matrix_real_engine`.** Use the real permission service: every role in A and B against A- and B-owned invoices for read/update/delete. A privileged roles allow on A; every B role, including B owner/admin, denies on A. This catches a role-only policy.
- **N4 `repository_scope_without_policy`.** Call the repository directly with `tenant_context = B` and A-id for find and update: no row, zero rows affected. Verifies the second line of defense independently of HTTP and policy.
- **N5 `forged_allow_defense_in_depth`.** Make the policy return allow for B→A (simulating a policy bug) and repeat N2/N6. The data layer or RLS must still prevent access, or the test must fail naming the permission layer as the sole guard.

**Cross-tenant writes with a state oracle**

- **N6 `cross_tenant_patch_no_state_change`.** B owner/admin, real engine, valid body, PATCH A-id. Assert refusal and read A's row through a separate privileged connection: every column, `tenant_id`, `updated_at`, version, line items, totals identical. No outbox/event/webhook rows.
- **N7 `cross_tenant_put_delete_no_state_change`.** Same for PUT and DELETE, including soft-delete flags and cascades.
- **N8 `tenant_mass_assignment`.** PATCH B's own invoice with `tenant_id: A`; assert it stays in B. POST with `tenant_id: A`; reject or create under B only. Repeat via nested lines and customer references.
- **N9 `bulk_mixed_tenant_atomicity`.** Send `[B-id, A-id]` and an all-A batch; assert whole-request rejection, no B row updated, no partial success. Also batch delete and import/upsert.

**Reads and entry points**

- **N10 `list_and_aggregate_scope`.** GET /invoices as each B role returns only B rows; counts, totals, sums, and pagination match B's ledger. Try `?tenant_id=A`, sorting by A's invoice number, search, cursors derived from A.
- **N11 `subresource_idor`.** From B: line items, PDF/download, attachments, events, comments, payments, audit trails of A-id. Uniform refusal; no A bytes, filenames, ETags, or metadata.
- **N12 `export_and_reports`.** CSV/PDF exports, scheduled reports, dashboards, and aggregates exclude A. Export jobs take tenant from authenticated context, not job parameters.
- **N13 `alternate_entry_points`.** Repeat on API v2, GraphQL, mobile, webhook replay, admin/support, import, and workers accepting invoice IDs.
- **N14 `path_and_method_tricks`.** Encoded IDs, duplicate slashes, case variants, UUID/integer confusion, `X-HTTP-Method-Override`, trailing segments must not bypass the guard.

**Auth and role matrix**

- **N15 `authentication_states`.** No credentials, malformed/expired/revoked/wrong-issuer token, deleted user: 401 on every method. Valid token with no role: 403, not 401.
- **N16 `same_tenant_role_matrix`.** A viewer reads but cannot write; A editor writes; A billing/service account only its scoped actions. Each denial checks state.
- **N17 `tenant_b_privileged_roles`.** B owner/admin/member/viewer each attempt read and write against A. B owner/admin are mandatory; they separate "tenant check" from "role check."
- **N18 `platform_admin_without_grant`.** Platform/support admin without break-glass is denied; with a grant, access is allowed, scoped, and audited. Tenant admins cannot reach platform routes.

**Denial side effects, disclosure, audit**

- **N19 `denial_is_side_effect_free`.** For every refusal: no invoice/line/payment change, no cache entry, email, or webhook. Snapshot the DB and spy that the write repository was never called.
- **N20 `denial_response_non_disclosure`.** Generic error bodies and headers; no A tenant name, ID, invoice number, amount, version, `Location`, or `ETag`. Foreign and absent IDs are indistinguishable.
- **N21 `denial_audit`.** Exactly one security event per denied cross-tenant attempt, with actor, session tenant, target tenant, action, decision, reason. A tenant user cannot read, alter, or delete it.

## Verify the verifier

A green negative is evidence only if it can fail. Run these mutants and record the kill matrix with commit and command:

- **M1:** remove the tenant predicate from the read query → N1/N10 must fail.
- **M2:** remove the tenant predicate from the update, and allow the policy → N4/N6 must fail.
- **M3:** policy allows all → N3/N17 must fail.
- **M4:** route returns 403/404 unconditionally → N1 controls must fail.
- **M5:** authorization after the UPDATE → N6/N19 must fail.
- **M6:** auth middleware disabled → N15 must fail.
- **M7:** audit writer made a no-op → N21 must fail.

A surviving mutant is a test present but not load-bearing. Line coverage of the guard is not a substitute; the assertion must observe the guard's removal.

## What can and cannot be claimed

The honest statement is: "With the permission service stubbed to deny, GET and PATCH on one invoice route return 404 and 403 for tenant B, and a session-less PATCH returns 401." That is all.

This is not evidence that production denies cross-tenant access, that queries and updates are tenant-scoped, that no cross-tenant write occurred, that other paths are protected, that role and tenant are both enforced, or that denials are audited. "Tenant isolation is covered" stays unclaimed until every claim-map row has a live, mutation-checked negative and the real path, including database state after refusal, is exercised.
