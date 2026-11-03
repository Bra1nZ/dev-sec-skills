---
name: negative-test-first
description: >
  Adversarial testing discipline for any product whose claims must hold.
  Use whenever you design a test plan, write or review tests for business
  rules, data invariants, persistence, concurrency, payments, validation,
  auth, permissions, or API contracts; whenever you decide whether a feature
  is done or a release is safe; and whenever a green suite is being used as
  evidence for a claim. A requirement is covered only when a test shows that
  violating it fails.
---

# Negative Test First

Find out whether the rule actually holds, then prove nothing slipped past it.
For every claim, some test must have tried to break it.

## Core rule

A requirement is covered only when a test shows that **violating it does not
work**. A test that asserts only the happy path proves nothing about the rule.
Ask: "Which test attempts the violation?" If none does, the claim is uncovered
— regardless of how much green the suite shows.

Write the negative first; the positive is the cheap half.

## Claim -> required negative

| Claim | Required negative |
| --- | --- |
| Feature works under condition C | The same feature outside C: empty, zero, one, many, maximum, wrong type, wrong order, expired, missing |
| Business rule ("a withdrawal cannot exceed the balance") | Exactly at the boundary, one past it, through another entry point, concurrently |
| Data invariant ("balance equals the sum of movements") | Rollback midway, crash between steps, retry, replay of an old message |
| State survives ("data is not lost on restart") | Kill/restart after the write is acknowledged, before the flush, during migration |
| Contract ("the API returns error E for bad input") | Each rejected input class individually; no partial write before the error |
| Concurrency ("no double spending") | Parallel attempts racing for the same resource, repeat delivery, two writers |
| Security ("only role X can write table T") | Role Y, role-less session, X's neighbors, and every alternative path |

A negative that is never attempted is a hope, not coverage.

## Workflow

1. **List claims.** Extract them from the README, requirements, invariants, API
   docs, threat model, and regulator mapping. Give each a stable ID.
2. **Pair each claim with its negative.** Name the violating test before the
   confirming test. A claim without one goes onto a visible, counted backlog.
3. **Enumerate classes, not examples.** Empty, one, many, at the limit, one
   past it, wrong type/order, duplicate, expired, malformed.
4. **Try every entry point.** Direct calls, prepared statements, nested calls,
   batch/import, admin, migration, recovery, background jobs.
5. **Classify who refused.** Assert error code, reason, and layer — your code,
   platform, driver, or typo. "Something failed" is not evidence your rule ran.
6. **Assert the world did not change.** After every expected refusal, check
   that nothing was created, charged, counted, written, or left half-applied.
7. **Verify the verifier.** Mutation-test the check, inject a no-op, or remove
   the guard: if the test still passes, it tests nothing. A test artifact is
   not evidence that the test can fail.
8. **Record evidence.** Command, result, artifact path, commit, environment,
   and exact scope. Use the strongest relevant channel: formal/model result,
   targeted negative test, property/fuzz run, static analysis, or review.
   Negative results stay visible.
9. **Gate the release.** Wait for the full supported matrix, or record exactly
   what passed where and what residual risk remains. Partial truth, never
   implied completeness.

## Patterns

### Classes and boundaries

"Invalid input rejected" proves nothing. Test each class separately. Off-by-one
lives exactly at the boundary; a random sample of bad values will miss it.

### Refusal classification and honest branching

Never pass on any exception. "Our rule refused with reason R" and "the platform
refused before our code ran" are different claims. If another build's platform
protects first, name the check as defense in depth in the test itself. A suite
that cannot tell you who refused will hide the day the platform stops doing it.

### Two evidence channels

Records written inside a failing transaction die with the rollback. If reliable
evidence of a failure matters, keep a second channel that survives it — server
log, syslog, stderr marker — and test both.

### Migrations and performance

Rerun negatives on migrated live data: an upgrade that silently widens
permissions is a regression with a green release note. For performance claims,
use interleaved A/B runs and server-side medians; absolute thresholds are valid
only in proven-quiet conditions.

## Security claims

A security claim with no negative test is not "partially covered": nobody has
checked it even once. The positive test ("admin can grant") is almost
worthless; the question is whether anyone else can.

- Test outsider, role-less, expired, and neighboring-role sessions.
- Test every path to the resource, not just the front door.
- Test audit trails adversarially: can the actor edit or delete their own?
- Test lockouts together with the unlock path; the unlock must be gated.
- Keep a machine-readable `claim -> mechanism -> test` map when auditors
  require traceability; every row needs a living test.

## Anti-patterns

1. Coverage theater: 100% line coverage, zero rejection inputs.
2. `assert raises Exception` without layer, code, or reason.
3. Treating a platform refusal as proof your mechanism works.
4. Asserting failure but not the absence of side effects.
5. One green run standing in for a platform/upgrade matrix.
6. Absolute performance thresholds on a loaded machine, retried until green.
7. A documented claim with no test in the traceability map.
8. A test that cannot fail being counted as coverage.

## Suite shape

- One suite per claim family; each check is named for the claim it kills.
- Fresh-install, migration, and recovery blocks.
- Known-secrets convention for fixtures; never real credentials.
- Honest platform branching, not silent skips.
- The claim list is the index: every claim names its negative test. A hole in
  the index is a hole in coverage.

See `README.md` for motivation. If the repository includes a standards
crosswalk, it lives at `references/standards-map.md`; the skill itself does not
depend on a standard.
