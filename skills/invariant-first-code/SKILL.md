---
name: invariant-first-code
description: >
  Invariant-first engineering for code with security, correctness, integrity,
  or availability claims: auth and permissions, persistence, transactions,
  migrations, concurrency, APIs, secrets, lifecycle, and release/supply
  chain. Use whenever you design or review a feature that must not be
  bypassed, must not lose or corrupt data, must not double-apply an
  operation, or must fail closed. Turn every claim into an explicit invariant,
  enforce it at one choke point, and prove the enforcement can actually fail.
---

# Invariant-First Code

Code is a set of invariants that someone believes hold. Make them explicit,
enforce them at a choke point, and test the enforcement adversarially. A guard
that exists on one path is not a property of the system.

## The core rule

For every invariant, answer:

1. **Statement** — what must always be true, in falsifiable terms.
2. **Enforcement point** — the single place that prevents violation.
3. **Failure mode** — what happens when enforcement is missing or errors:
   deny, abort, roll back, or degrade safely. Never allow-by-default.
4. **Evidence** — the negative test, analysis, or proof that shows a
   violation attempt fails.
5. **Scope** — platforms, versions, actors, and paths covered.

If the invariant has no enforcement point or no violation test, it is a wish.

## Invariant map

Keep a map next to the design or in `references/invariant-template.md`:

| ID | Invariant | Enforcement point | Failure mode | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| I-01 | No session writes without a valid capability | `authorize_write()` | deny | T-04..T-09 | all write paths |

Add invariants for:

- **Authorization:** deny by default; no path bypasses the check; role-less,
  expired, neighboring, and admin actors are distinct cases.
- **Data integrity:** constraints, transactions, idempotency, migration
  ordering, backup/restore, crash recovery.
- **Concurrency:** one writer per resource, leases and fencing tokens,
  retries, duplicate delivery, stale workers.
- **Lifecycle:** initialization before use, cleanup on every exit path,
  secret rotation, zeroization of sensitive buffers.
- **Contracts:** typed errors, no partial writes, no secret leakage, stable
  behavior at boundaries.
- **Supply chain:** pinned dependencies, provenance, SBOM, reproducible
  builds, no secrets in artifacts.

## Design for fail-closed

- The default is deny. An error, timeout, missing configuration, unknown
  role, or unavailable policy service must not widen access.
- Put the check at the narrowest choke point that every path must cross.
  Do not duplicate policy in handlers; duplicated policy drifts.
- Separate authentication, authorization, and audit. A logging failure must
  not silently disable authorization.
- Treat "not found", "not supported", and "not configured" as distinct
  outcomes; do not collapse them into allow.
- If the platform provides defense in depth, keep your check and label it as
  defense in depth. Do not rely on the platform as the only guard.
- Make bypasses explicit and privileged: migrations, maintenance mode,
  recovery, and admin tools need their own gated path, not an ambient flag.

## Authorization invariants

- Enumerate every entry point: direct calls, prepared statements, nested
  calls, batch operations, imports, admin APIs, background jobs, and
  migrations.
- Test the outsider cases: wrong role, no role, expired session, revoked
  capability, neighboring tenant, object owner, admin without the specific
  grant.
- Test the object-level check, not only the route-level check. A user who can
  reach an endpoint must not automatically reach every object.
- Audit writes go through one channel; test whether the actor can modify or
  delete their own trail.
- Lockout and rate-limit unlock paths are permission-gated too.

## Data and transaction invariants

- Enforce invariants in the database where concurrent writers can violate
  them, not only in application code.
- A refused operation must leave no partial write. Check the side effects
  after every expected failure.
- Make retries idempotent with a stable key; "exactly once" is a protocol
  property, not a wish. Design for at-least-once delivery.
- Migrations run in a defined order, are restartable, and preserve
  constraints. Rerun negative tests on migrated live data.
- Backups are not evidence until a restore has been tested. Record the
  restore drill, not only the backup job.

## Concurrency invariants

- Name the resource, the contention, and the serialization mechanism.
- Prefer database constraints and row locks to application-level check-then-
  act. Check-then-act is a race unless the check and act are atomic.
- Use fencing tokens or monotonic epochs for leases and stale workers. A
  worker that lost its lease must not commit.
- Test duplicate delivery, retry storms, two writers, and a worker paused
  between check and write.
- A lock without a timeout is an availability bug; a timeout without
  correctness is a data bug.

## Interfaces and errors

- Define the error contract: which inputs are rejected, with which code, and
  whether any state changed.
- Do not leak secrets, tokens, internal paths, or stack traces in errors.
- Do not turn an internal failure into a success-shaped empty result.
- Validate at the boundary, then keep the validated representation; do not
  re-parse untrusted input in deeper layers.
- Batch and bulk paths need the same checks as single-item paths.

## Lifecycle and secrets

- Initialize before use; clean up on success, error, cancellation, and
  timeout paths.
- Zero or wipe sensitive buffers where the platform allows it; do not rely on
  garbage collection for secrets.
- Load secrets from the deployment secret store, never from source,
  fixtures, logs, or build artifacts.
- Rotation must invalidate old credentials within the stated window. Test
  the stale-credential case.
- Destructors and cleanup must be idempotent; a failed cleanup must be
  visible, not silent.

## Platform contracts

- Declare supported versions and required privileges. A behavior that depends
  on an unsupported configuration is out of scope, not "works on my machine".
- Test on every supported platform, or state exactly which platform was
  tested and which was not.
- When the platform refuses first, report it honestly as defense in depth.
- Pin the platform behavior you rely on with a test; upgrades can change it.

## Build and supply chain

- Pin dependencies and build inputs; record the lockfile and toolchain.
- Generate an SBOM and provenance for release artifacts.
- Run secret scanning and dependency vulnerability checks in CI.
- Make builds reproducible enough to detect tampering; record the commit,
  builder, and inputs.
- Do not ship debug endpoints, default credentials, or permissive CORS by
  accident.

## Verification

- For each invariant, write the negative test first and verify it fails when
  the enforcement is removed.
- Use static analysis for whole-program properties, dynamic tests for
  behavior, fuzzing for parsers and state machines, and sanitizers for memory
  and undefined behavior. Record which tool covered which invariant.
- Mutation-test critical guards or inject a no-op; a test that cannot fail is
  not evidence.
- Verify the verifier: check the oracle, the fixture, and the assertion, not
  only the exit code.
- Record residual risk: what was not tested, what was out of scope, and what
  remains open.

## Review checklist

- Every security and integrity claim has an invariant ID and an enforcement
  point.
- Every enforcement point is on every path; no ambient bypass.
- Failure is closed, visible, and leaves no partial state.
- Outsider, role-less, expired, and neighboring-object cases are tested.
- Concurrency is enforced atomically, with fencing for stale workers.
- Errors do not leak secrets and do not convert failure into success.
- Cleanup runs on every exit path; secrets are not logged.
- Supported platforms and privileges are stated.
- Supply chain inputs are pinned and scanned.
- The negative test fails when the guard is removed.

## Anti-patterns

1. **Check on one path.** The guard exists in the HTTP handler but not in the
   batch job, import, or migration.
2. **Allow on error.** A policy service timeout becomes "no policy, allow".
3. **Check-then-act.** A race between the permission check and the write.
4. **Partial write on refusal.** The error is correct; the state is not.
5. **Platform as the only guard.** Defense in depth is good; sole defense is
   fragile.
6. **Silent cleanup failure.** The resource leaks and nobody sees it.
7. **Secret in the log.** The error message includes the token or password.
8. **Unfalsifiable test.** The test passes even when the mechanism is removed.
9. **Stale scope.** "Tested" on an unsupported version or configuration.
10. **Supply-chain blind spot.** Dependencies and build inputs are unpinned.

Use `references/review-checklist.md` for a compact review pass. If the
repository includes a standards crosswalk, it lives at
`references/standards-map.md`; the skill itself does not depend on a standard.

Keep the design proportional to the request. Group tests by invariant and
mark the release-blocking ones; do not turn a five-invariant review into a
45-test catalogue. When the platform is not specified, label the chosen
platform as an assumption or ask; do not present invented versions as facts.
