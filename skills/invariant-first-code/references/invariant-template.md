# Invariant Template

Use one block per invariant. Keep it next to the design or link it from the
claim ledger.

```markdown
### I-01: <falsifiable invariant>

- **Statement:** <what must always be true>
- **Enforcement point:** <single function, constraint, policy, or protocol>
- **Failure mode:** deny / abort / rollback / safe degrade
- **Paths covered:** <HTTP, batch, import, admin, migration, recovery>
- **Actors covered:** <roles, role-less, expired, neighboring tenant, admin>
- **Concurrency:** <lock, constraint, lease, fencing token>
- **Evidence:** <negative test IDs, analysis, proof>
- **Scope:** <platforms, versions, configuration>
- **Out of scope:** <privileged actors, unsupported configs>
- **Residual risk:** <what remains open>
```

## Invariant map

```markdown
| ID | Invariant | Enforcement point | Failure mode | Evidence | Scope |
| --- | --- | --- | --- | --- | --- |
| I-01 |  |  |  |  |  |
```

## Questions that expose missing invariants

1. What can a user do that they must never be able to do?
2. Which path reaches the protected resource without the check?
3. What happens if the check itself fails, times out, or is misconfigured?
4. What happens if the process dies between the check and the write?
5. What happens if the operation is retried, duplicated, or replayed?
6. What happens if an old worker or stale session acts after rotation?
7. What happens on migration, restore, or rollback?
8. What does the error path leave behind?
9. What does the log contain when the operation fails?
10. Which supported platform behaves differently, and is that tested?

## Enforcement-point review

- Is the check at the narrowest point every path must cross?
- Is policy duplicated anywhere else? If yes, which copy is authoritative?
- Can a caller skip the check by using a lower-level API?
- Is the default deny, including on error and missing configuration?
- Is the check atomic with the action it protects?
- Does the check cover object-level authorization, not only route-level?
- Is the failure visible to the operator without leaking secrets?
- Does the check have a negative test that fails when removed?
