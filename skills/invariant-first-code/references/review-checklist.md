# Code Review Checklist

A compact pass for changes that carry security, integrity, or availability
claims. Skip nothing silently; mark an item N/A with a reason.

## Claims and invariants

- [ ] The change states which invariants it must preserve or establish.
- [ ] Each invariant has an enforcement point and a negative test.
- [ ] The test fails when the enforcement is removed or replaced by a no-op.
- [ ] The scope and unsupported configurations are stated.

## Authorization

- [ ] Default is deny, including on error, timeout, and missing policy.
- [ ] The check is on every path: HTTP, batch, import, admin, migration,
      recovery, background job.
- [ ] Object-level authorization is checked, not only route-level.
- [ ] Role-less, expired, revoked, neighboring-tenant, and admin cases are
      tested.
- [ ] No ambient bypass flag; privileged paths are explicit and gated.
- [ ] Audit writes go through one channel; the actor cannot edit their trail.

## Data integrity

- [ ] Constraints are enforced where concurrent writers can violate them.
- [ ] Refusal leaves no partial write.
- [ ] Retries are idempotent with a stable key.
- [ ] Migrations are ordered, restartable, and preserve constraints.
- [ ] Negative tests run on migrated data.
- [ ] Restore has been tested, not only backup.

## Concurrency

- [ ] The resource, contention, and serialization mechanism are named.
- [ ] Check-then-act is atomic or replaced by a constraint/lock.
- [ ] Leases use fencing tokens or monotonic epochs.
- [ ] Stale workers cannot commit after losing a lease.
- [ ] Duplicate delivery and retry storms are tested.
- [ ] Locks have timeouts; timeouts do not sacrifice correctness.

## Interfaces and errors

- [ ] The error contract is explicit: code, reason, state change.
- [ ] Errors do not leak secrets, tokens, paths, or stack traces.
- [ ] Internal failure is not converted into a success-shaped empty result.
- [ ] Validation happens at the boundary; untrusted input is not reparsed
      deeper.
- [ ] Bulk paths apply the same checks as single-item paths.

## Lifecycle and secrets

- [ ] Initialization precedes use; cleanup runs on success, error,
      cancellation, and timeout.
- [ ] Sensitive buffers are wiped where the platform allows.
- [ ] Secrets come from the deployment secret store, not source or fixtures.
- [ ] Rotation invalidates old credentials within the stated window.
- [ ] Stale-credential behavior is tested.
- [ ] Cleanup is idempotent and failures are visible.

## Platform and supply chain

- [ ] Supported versions and required privileges are declared.
- [ ] Behavior that depends on an unsupported configuration is out of scope.
- [ ] Every supported platform is tested, or the untested ones are named.
- [ ] Platform behavior is pinned by a test.
- [ ] Dependencies and build inputs are pinned.
- [ ] SBOM and provenance are generated for release artifacts.
- [ ] Secret scanning and dependency checks run in CI.
- [ ] No debug endpoint, default credential, or permissive CORS ships.

## Verification

- [ ] Negative tests cover boundary, outsider, concurrency, and failure-path
      cases.
- [ ] Static analysis findings are triaged, not just counted.
- [ ] Dynamic tests and fuzzing cover the state machines and parsers.
- [ ] Sanitizers are enabled where memory safety matters.
- [ ] Critical guards are mutation-tested or no-op tested.
- [ ] Residual risk is recorded in the release note.
