# Security and test status

This section states what was executed, on which platforms, and what remains open. Ledger IDs refer to the claim ledger below.

**Status summary:** 8 claims — 3 `tested`, 5 `open`; no claim has a stronger status.

**Trust boundary.** The claims below apply to PostgreSQL 14, 15, 16, and 17 under the documented configuration. Superuser and DBA are outside the threat model: no claim is made about their actions, and they are not covered by any test result here.

**Tenant writes.** Negative tests T-04..T-11 attempt cross-tenant writes as role Y and as a role-less session; on PostgreSQL 14–17 those attempts are rejected. Status: `tested` (C-01, C-02). Coverage is limited to the entry points those tests exercise. The tests do not establish tenant isolation for reads, for other roles, or for entry points outside T-04..T-11; that broader property remains `open` (C-03). The individual test-to-actor mapping and the exact enforcement path are not recorded in the supplied evidence.

**Test suite.** 876 of 876 executed tests passed on the PostgreSQL 14–17 matrix. Status: `tested` (C-04). This is a pass count, not a coverage statement: the result does not show that every supported behavior was exercised (C-05, `open`). Per-version counts, commit, run date, and the command are not recorded in the supplied evidence (E-01).

**Known gaps.**

- ASAN was not rerun after the CE-3 fix. No memory-safety result applies to the post-fix revision of the C layer (C-06, `open`).
- Stale-worker behavior after `rotate_session_secret()` is untested. Whether a worker holding pre-rotation session state continues to accept it is unknown (C-07, `open`).
- No FSTEC 76 audit was performed. No compliance or audit status is claimed; any control mapping is documentation, not an audit result (C-08, `open`).

**Not claimed.** This document does not make a general security assertion, does not state that testing covers every supported behavior, does not state that tenant isolation holds for every actor and path, and does not state that the product meets FSTEC 76. Each of those requires evidence that does not exist in the current record.

---

# Claim ledger

| ID | Claim | Mechanism | Evidence | Scope / TCB | Status | Limitations | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 | Role Y cannot perform a cross-tenant write through the paths exercised by T-04..T-11 | Tenant-write enforcement in the extension; exact code path not cited in the supplied materials | Negative tests T-04..T-11 (collectively cover role Y); artifact path and command not recorded (E-02) | PostgreSQL 14–17; role Y; tested entry points. Superuser and DBA excluded | `tested` | Individual test mapping, commit, and run date not recorded; removal-sensitivity of the guard not demonstrated | not recorded |
| C-02 | A role-less session cannot perform a cross-tenant write through the paths exercised by T-04..T-11 | Tenant-write enforcement in the extension; exact code path not cited in the supplied materials | Negative tests T-04..T-11 (collectively cover role-less sessions); artifact path and command not recorded (E-02) | PostgreSQL 14–17; role-less session; tested entry points. Superuser and DBA excluded | `tested` | Individual test mapping, commit, and run date not recorded; removal-sensitivity of the guard not demonstrated | not recorded |
| C-03 | Tenant isolation holds for all supported actors, access modes, and entry points | Not established beyond the tenant-write checks exercised by T-04..T-11 | None for reads, other roles, or entry points outside T-04..T-11 | All supported configurations on PostgreSQL 14–17; superuser and DBA excluded | `open` | Only cross-tenant writes for role Y and role-less sessions are covered; reads, context propagation, other roles, and untested paths are unassessed | n/a — no artifact |
| C-04 | 876 of 876 executed tests passed on the PostgreSQL 14–17 matrix | Test suite execution; command not recorded | Suite result E-01; per-version breakdown, commit, and date not recorded | PostgreSQL 14–17; OS and configuration not recorded | `tested` | Pass count only; does not establish coverage of all supported behavior; evidence is not reproducible as recorded | not recorded |
| C-05 | The test suite covers all supported behavior | No coverage matrix or mapping from supported behaviors to tests | None | All supported behavior on PostgreSQL 14–17 | `open` | A 876/876 pass count is not coverage evidence | n/a — no artifact |
| C-06 | The C layer is free of memory-safety defects at the post-CE-3 revision, as checked by ASAN | ASAN instrumentation of the C layer | ASAN was not rerun after CE-3; no post-fix artifact exists (E-03) | C layer, current revision; build configuration not recorded | `open` | Any prior ASAN result predates CE-3 and does not apply to the post-fix revision | n/a — not rerun |
| C-07 | `rotate_session_secret()` terminates sessions held by stale workers | Session-secret rotation; worker invalidation behavior is not established | None; behavior untested (E-04) | Pooled or stale workers on PostgreSQL 14–17; configuration not recorded | `open` | No test establishes whether a stale worker accepts pre-rotation sessions | n/a — not tested |
| C-08 | The extension meets the requirements of FSTEC 76 | Control mapping at most; no audit performed | None; no FSTEC audit (E-05) | FSTEC 76 requirements; class and scope not specified in the supplied evidence | `open` | A mapping is not an audit; no auditor report exists | n/a — no audit |

---

# Open claims and residual risk

The following are risks, not results:

- **C-03 — wider tenant isolation.** Cross-tenant reads, context propagation, actors other than role Y and role-less sessions, and entry points outside T-04..T-11 have no recorded negative evidence.
- **C-05 — coverage.** The suite size and pass count do not show which supported behaviors are exercised. A coverage matrix is absent.
- **C-06 — C-layer memory safety.** The CE-3 fix has no post-fix ASAN run. Do not describe the current revision as ASAN-clean.
- **C-07 — secret rotation.** No test shows whether `rotate_session_secret()` invalidates sessions cached by stale workers. A worker may continue to accept a pre-rotation session; the outcome is unknown.
- **C-08 — FSTEC 76.** No audit was performed. Do not publish a compliance statement, certificate reference, or readiness badge.

**Before a release claim:** record the commit, run date, command, and artifact path for E-01 and E-02; rerun ASAN after CE-3; add a stale-worker test for `rotate_session_secret()`; and either commission an FSTEC 76 audit or keep compliance out of release notes.

---

# Scope and assumptions

- **Platforms:** PostgreSQL 14, 15, 16, and 17 only. Other majors are not covered.
- **Configuration:** the documented configuration; non-default or unsupported configurations are not covered.
- **Privileged actors:** superuser and DBA are outside the threat model and are excluded from every claim.
- **Threat model:** the supplied materials state only the superuser/DBA exclusion. They do not contain a full threat model, so no claim here should be read as one.
- **Evidence record:** run dates and commits are absent from the supplied artifacts; every `tested` claim carries that reproducibility gap.
- **External validation:** no FSTEC 76 audit or third-party assessment was performed.

---

# Evidence index

| Ref | Artifact | Command / procedure | Commit | Environment | Date | Result |
| --- | --- | --- | --- | --- | --- | --- |
| E-01 | Test suite output; path or CI URL not supplied | Not recorded | Not recorded | PostgreSQL 14–17; OS and configuration not recorded | Not recorded | 876/876 passed on the matrix; per-version breakdown absent |
| E-02 | Negative tests T-04..T-11; source path and runner not supplied | Not recorded | Not recorded | PostgreSQL 14–17; configuration not recorded | Not recorded | Cross-tenant write attempts by role Y and role-less sessions rejected |
| E-03 | ASAN report; not supplied | Not recorded | Pre-CE-3 revision only | C layer; build configuration not recorded | Not recorded | Not rerun after CE-3; no post-fix result |
| E-04 | None | None | n/a | n/a | n/a | Stale-worker behavior after `rotate_session_secret()` not executed |
| E-05 | None | None | n/a | n/a | n/a | No FSTEC 76 audit performed |

The entries above cite artifacts that were not supplied with the source material. Until E-01 and E-02 carry a commit, date, command, and artifact path, their `tested` status rests on the reported result and is not independently reproducible from this document.

---

# Disposition of prior wording

| Prior statement | Disposition |
| --- | --- |
| General security assertion | Removed. Replaced by scoped statements C-01..C-04 and explicit non-claims. |
| Coverage-of-all-behavior assertion | Removed. Replaced by the exact matrix pass count (C-04); coverage remains `open` (C-05). |
| Absolute test-pass statement | Replaced by 876/876 on PostgreSQL 14–17, with the missing commit, date, and command recorded as limitations (E-01). |
| Tenant-isolation claim | Narrowed to cross-tenant writes exercised by T-04..T-11 for role Y and role-less sessions (C-01, C-02); wider isolation remains `open` (C-03). |
| FSTEC 76 compliance statement | Withdrawn. No audit was performed (C-08, `open`). |
