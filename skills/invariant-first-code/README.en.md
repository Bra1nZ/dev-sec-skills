# invariant-first-code

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: agent skill](https://img.shields.io/badge/format-SKILL.md-orange)](SKILL.md)
[![Focus: fail closed](https://img.shields.io/badge/focus-fail%20closed-2ea44f)](SKILL.md)

An agent skill for designing and reviewing code with security, correctness,
integrity, or availability claims: auth and permissions, persistence,
transactions, migrations, concurrency, APIs, secrets, lifecycle, release, and
supply chain.

It is for the gap between "we added a check" and "it cannot be bypassed". A
guard on one path is not a property of the system. A check that fails open is
not a check. A test that passes without the guard is not evidence.

## The core idea

Code is a set of invariants that someone believes hold. Make them explicit,
enforce them at a choke point, and test the enforcement adversarially.

For every invariant, answer:

1. **Statement** — what must always be true, in falsifiable terms.
2. **Enforcement point** — the single place that prevents violation.
3. **Failure mode** — what happens when enforcement is missing or errors:
   deny, abort, roll back, or degrade safely. Never allow-by-default.
4. **Evidence** — the negative test, analysis, or proof that shows a
   violation attempt fails.
5. **Scope** — platforms, versions, actors, and paths covered.

If the invariant has no enforcement point or no violation test, it is a wish.

## What is inside

- `SKILL.md` — invariant map, fail-closed design, authorization, data and
  transaction invariants, concurrency, interfaces/errors, lifecycle/secrets,
  platform contracts, build/supply chain, verification, review checklist,
  anti-patterns.
- [`references/invariant-template.md`](references/invariant-template.md) —
  invariant block, map, and questions that expose missing invariants.
- [`references/review-checklist.md`](references/review-checklist.md) — a
  compact pass for security-sensitive changes.

## Key rules

- **Default deny.** An error, timeout, missing policy, unknown role, or
  unavailable service must not widen access.
- **One enforcement point.** Do not duplicate policy across handlers; copies
  drift.
- **Every path.** HTTP, batch, import, admin API, background job, migration,
  recovery — the same protected resource.
- **Object-level authorization.** Reaching an endpoint does not mean reaching
  every object.
- **Atomicity.** Check-then-act is a race unless the check and act are atomic.
- **Fencing.** A stale worker must not commit after losing its lease.
- **No partial write.** A refusal leaves no half-state.
- **Verify the verifier.** Remove the guard or replace it with a no-op: the
  test must fail. Otherwise it is not evidence.

## Example

Bad:

> Added a role check in the HTTP handler. Tests pass.

Good:

> Invariant I-01: no write to T succeeds without a capability. Enforcement
> point: `authorize_write()`; default deny on policy error. Covered paths:
> HTTP, batch, import, admin, and migration. Role Y, role-less, expired,
> neighboring tenant, and object owner are rejected (T-04..T-11). The test
> fails when the guard is removed. Scope: PostgreSQL 14–17; superuser/DBA are
> outside the model.

## Install

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

The skill activates when you need to design or review a feature that must not
be bypassed, must not lose or corrupt data, must not double-apply an operation,
or must fail closed.

## Related skills

- [`negative-test-first`](../negative-test-first/SKILL.md) turns each
  invariant into a violation attempt.
- [`evidence-first-docs`](../evidence-first-docs/SKILL.md) records the
  mechanism, evidence, scope, and status.
- The standards crosswalk is in
  [`references/standards-map.md`](../../references/standards-map.md).

## License

MIT — see [LICENSE](LICENSE). Third-party standards keep their own
licenses.
