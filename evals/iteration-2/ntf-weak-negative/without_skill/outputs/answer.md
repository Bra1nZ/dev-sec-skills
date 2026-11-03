# Review: Negative-Test Suite for Multi-Tenant Invoice API

## Verdict

The suite is not a tenant-isolation suite. It is a three-case check that one controller maps a mocked `deny` to a response code on two verbs. The claim "negative tests pass and tenant isolation is covered" does not follow from the evidence. At least one of the three assertions encodes a security regression (the 403 on cross-tenant PATCH is an existence oracle), one is probably semantically wrong (401 for an authenticated role-less session), and all three are tautological because the only authorization input is a mock hardcoded to deny.

## What each test actually establishes

**Test 1 — GET /invoices/A-id as B, expect 404.** Proves that, for this route and this fixture, a deny decision is translated into 404 and that the route is not anonymously reachable. It does not prove the invoice exists, that it belongs to A, that the policy service was consulted, that it was consulted with B's tenant and A's resource, that the decision came from tenancy rather than from the ID being absent, or that the response body and headers are indistinguishable from a genuinely nonexistent ID.

**Test 2 — PATCH /invoices/A-id as B with valid body, expect 403.** Proves that deny maps to 403 on PATCH. It proves almost nothing about isolation, and it actively contradicts Test 1: the same cross-tenant resource is "not found" on read and "forbidden" on update. That asymmetry is the classic enumeration oracle. An attacker who receives 404 on GET can issue a cheap PATCH (or any non-GET verb) and distinguish "exists, belongs to someone else" from "does not exist." If the production code really behaves this way, the test is asserting a vulnerability. If production returns 404 for both, the test is asserting the wrong contract and should be failing.

**Test 3 — role-less session PATCH, expect 401.** Proves that a session the test classifies as role-less gets 401 on this one verb. It conflates authentication with authorization. An authenticated principal with no role should normally receive 403; 401 means credentials are missing or invalid and should carry `WWW-Authenticate`. If the test's "role-less session" is in fact anonymous, then the name is misleading and the suite has no test for the authenticated-but-unauthorized case at all. Either way, GET, DELETE, and collection endpoints are untested for this boundary.

## The structural weakness: a deny-only mock

Every test mocks the permission service to return deny. That makes the authorization input a constant, so the tests verify only the deny-to-status-code plumbing. They cannot distinguish a correct policy from a policy that denies everything, from a handler that never calls the policy at all but has a deny-shaped default, or from a route-level WAF returning 404/403 unconditionally. Concretely:

- **No allow path.** There is no positive control showing tenant A can GET and PATCH its own invoice, that A's list contains only A's invoices, or that a legitimately cross-tenant support role is allowed and audited. Without that, a deployment that rejects all requests passes the suite.
- **No argument assertion.** Nothing checks that the policy was called with `(subject=B, resource=A-id, action=read|update)`. A handler that calls the PDP with the wrong tenant, or with a tenant derived from the request body, passes.
- **The tenant predicate is untested.** If the code contains `if invoice.tenant_id != caller.tenant_id: raise NotFound` and someone deletes that line, all three tests still pass because the mock denies upstream. The suite's mutation score on the tenancy logic is zero while line coverage looks respectable.
- **Ordering is untested.** Nothing shows authorization happens before the database read. If the handler loads the invoice, writes a read receipt, or populates a cache before checking, the deny still maps to 403 while side effects and timing already leaked.
- **Deny caching is untested.** If PDP decisions are cached by resource ID without tenant in the key, B's deny can poison A's allow. The suite would not notice.

## Missing negative tests

The following are the minimum additions. Each should assert status, response body shape, relevant headers, absence of state change, and (where a fake PDP is used) the call arguments.

**Existence and enumeration**
1. Differential pair: request an existing other-tenant ID and a random nonexistent ID with the same verb; require byte-identical bodies, identical headers, and comparable latency distributions. Run for GET, HEAD, PATCH, DELETE.
2. Uniform 404 contract across all verbs for cross-tenant resources, or a documented uniform 403; forbid the current mix.
3. Sequential-ID enumeration: confirm rate limiting or another control prevents harvesting IDs via the 404/403 oracle.
4. HEAD and OPTIONS on A-id: no existence or method metadata leak.

**Collection and query surface**
5. `GET /invoices` as B returns zero of A's rows, including when filters, sort, search, and date ranges are supplied.
6. Aggregate endpoints (counts, totals, dashboards, reports) exclude A's data.
7. Tenant override attempts: `?tenant_id=A`, `?tenantId=A`, duplicate tenant headers, `X-Tenant-ID` override, body-supplied tenant, and JWT claim that disagrees with the path/header. Expect 400/403, never a default tenant.
8. Cursor and pagination tampering: replay A's cursor under B's session; cursors must be opaque and tenant-bound.
9. Eager-load/expand parameters (`?include=customer`, `?expand=payments`) must not traverse into A's related objects.

**Write surface**
10. DELETE /invoices/A-id as B → 404 (or the chosen uniform code), and the row still exists afterward.
11. POST /invoices as B with `tenant_id: A` in the body or with A's `customer_id`/`payment_id`; must not create in A and must not confirm A's related-object existence via a distinct error.
12. PATCH mass assignment: `tenant_id`, `owner_id`, `status`, `total`, `paid_at` must be rejected or ignored; assert the persisted row is unchanged.
13. Bulk/batch endpoints with a mixed array of A and B IDs: all-or-nothing or per-item 404, with no partial mutation and no per-item existence signal.
14. Idempotency-key replay across tenants, and duplicate/clone/copy endpoints.
15. Subresources and alternate identifiers: `/invoices/A-id/lines`, `/pdf`, `/attachments`, `/events`, `/audit`, plus lookup by invoice number, external ID, or slug.

**Authentication and role boundaries**
16. No session at all on every verb → 401 with `WWW-Authenticate`, no default tenant.
17. Authenticated, no role → 403, distinctly from 401.
18. Authenticated with a read-only role attempting PATCH/DELETE → 403.
19. Expired, revoked, and wrong-audience tokens; API key from tenant A against B's routes; signed URL for A's attachment redeemed under B.

**Side channels and state**
20. Response-body parity: no stack traces, SQL fragments, tenant names, or field echoes in deny responses.
21. No partial write, no `updated_at` bump, no audit row readable by B after a denied PATCH.
22. Denied attempts are logged/attributed to B (detection, not prevention).
23. Shared-cache test: prime as A with a 200, request the same URL as B, require B's own 404 rather than A's cached body.
24. Timing: compare deny-for-existing-other-tenant against deny-for-nonexistent; a stable difference is an oracle even with identical status codes.

## Claim map

| Claim | What would prove it | What the suite shows | Verdict |
|---|---|---|---|
| "Negative tests pass" | Tests execute and assert meaningful invariants | Three assertions on status codes, one of which encodes an oracle | True but security-irrelevant |
| "Cross-tenant read is blocked" | Existing A-owned fixture, real tenant-derived decision, no body leak, no side channel | Deny mock → 404 on one route | Partially, conditionally |
| "Cross-tenant write is blocked" | Same, plus no state change, plus uniform 404 | Deny mock → 403, which discloses existence | Not proven; likely harmful |
| "Tenant isolation is covered" | Coverage of every tenant-scoped query, collection, subresource, and write path | Two verbs on one resource | False |
| "Authorization is enforced" | Allow and deny paths, PDP call-argument assertions, real policy | Only the deny branch of the plumbing | Not proven |
| "Unauthenticated access is rejected" | 401 without credentials on all verbs, with `WWW-Authenticate` | One PATCH case, ambiguous 401/403 semantics | Not proven |
| "Denied writes have no effect" | Read-back and audit assertions after denial | No state assertions | Not tested |
| "Errors do not leak data" | Body/header/timing parity between existing-other-tenant and nonexistent IDs | Status only | Not tested |
| "Deny is audited" | Log/metric assertion attributed to B | Nothing | Not tested |

## What to change before re-running

Make the authorization input real. Replace the hardcoded deny with a table-driven fake policy that computes allow/deny from `(subject tenant, resource tenant, action, role)`, seed one invoice owned by A and one by B, and assert the fake was called with the expected arguments. Add the paired positive controls: A gets 200 on its own invoice, A's list contains exactly its rows, and a support role with an explicit grant succeeds and is audited. Pick one existence contract — 404 for cross-tenant on all verbs is the safer default — and enforce it with the differential pair from item 1. Then add the collection, subresource, bulk, alternate-identifier, and side-channel cases above.

A negative test is only evidence when the negative is caused by the property under test. Here the negative is caused by the mock, so the suite demonstrates response-code mapping, not tenant isolation. The claim should be withdrawn and the suite rebuilt around a real policy fixture plus positive controls.
