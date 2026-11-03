# Evidence Templates

Copy and adapt. Keep the fields; they are the minimum for a reproducible
claim.

## Claim ledger

```markdown
| ID | Claim | Mechanism | Evidence | Scope / TCB | Status | Limitations | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 |  |  |  |  |  |  |  |
```

Status values: `proven`, `model-checked`, `tested`, `static-refinement`,
`reviewed`, `open`.

## Evidence index

```markdown
## Evidence index

| Ref | Artifact | Command / procedure | Commit | Environment | Date | Result |
| --- | --- | --- | --- | --- | --- | --- |
| E-01 |  |  |  |  |  |  |
```

Rules:

- `Artifact` is a path or URL, not a tool name.
- `Command / procedure` must be reproducible by a reviewer.
- `Commit` is the exact revision the evidence applies to.
- `Environment` names OS, runtime, database, platform version, and relevant
  configuration.
- `Result` is the observed outcome, including failures and refusals.

## Claim block

Use this shape when a claim needs more than a table row:

```markdown
### C-01: <falsifiable claim>

- **Status:** `tested`
- **Mechanism:** <where the enforcement lives>
- **Evidence:** <artifact path>, <command>, <date>, <commit>
- **Scope:** <platforms, versions, actors, paths>
- **Out of scope:** <privileged actors, unsupported configs, unmodeled paths>
- **Limitations:** <model-to-code gap, bounds, known failures>
- **Last verified:** YYYY-MM-DD
- **Negative check:** <test that fails when the mechanism is removed>
```

## Release note

```markdown
## Release <version>

### Claims supported by this release

| Claim | Status | Evidence | Scope |
| --- | --- | --- | --- |
|  |  |  |  |

### Open claims and residual risk

- ...

### Evidence freshness

- Last full verification: <date>, commit <sha>
- Not rerun for this release: <list and reason>
```

Do not write "all tests pass". Write the exact matrix and the exact counts.

## Review record

```markdown
## Review <date>

- Reviewer:
- Scope:
- Artifacts read:
- Claims checked:
- Claims rejected or downgraded:
- Open questions:
- Decision: approve / approve with conditions / reject
```

## Negative-result record

```markdown
### N-01: <what was attempted>

- **Hypothesis:** <what should have failed>
- **Attempt:** <input, path, concurrency, environment>
- **Observed:** <result>
- **Why it did not fail:** <mechanism, platform refusal, test gap>
- **Conclusion:** <covered / not covered / inconclusive>
```

Negative results are evidence. Keep them visible; do not delete them when the
happy path turns green.
