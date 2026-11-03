# rbac 1.4.12 — Release Notes

**Status:** Draft for release review
**Prepared:** 2026-11-02
**Basis:** Release facts supplied for rbac 1.4.12. No tests were re-run for this draft. The only named test artifact is `t/131`; other results are reported without artifact paths, commands, commits, or dates.

## Release summary

This note covers three changes in rbac 1.4.12:

- **CE-3 — context leak fix.** The context is dropped before `RAISE` on the failure path, so a failure does not leave the context installed behind the error. Regression test `t/131` reports 10/10 (`tested`; scope: the path exercised by `t/131`, environment not stated).
- **CE-4 — fail-closed behavior for out-of-supported configurations.** The release changes out-of-supported configurations to fail closed. This is an implementation change; no test or analysis artifact was supplied (`open`).
- **CE-7 — `PARALLEL RESTRICTED` documentation.** CE-7 is documented as `PARALLEL RESTRICTED`. This is a documentation/declaration change; parallel-worker runtime behavior has no test evidence in the supplied facts (`open`).

The full installcheck suite reports 876/876 on PostgreSQL 14–17 (`tested`). The ASAN run reports 866/866 on a pre-CE-3 revision; ASAN was not rerun after CE-3. The result does not cover the CE-3 change or this release. The stale-worker-after-secret-rotation scenario has no test evidence.

## Claim summary

- `tested`: 2 claims with supplied results (C-01 CE-3 regression; C-02 installcheck).
- `tested` but stale: 1 claim (C-03 ASAN, pre-CE-3; does not cover 1.4.12).
- `open`: 3 claims (C-04 CE-4 fail-closed; C-05 CE-7 runtime; C-06 stale worker after secret rotation).
- `proven`: 0.
- `model-checked`: 0.
- `static-refinement`: 0.
- `reviewed`: 0.

The 10/10 and 876/876 results are test results. They are not formal proof and do not establish properties outside their stated scope.

Release gate: C-01 and C-02 are supported by the supplied test results. C-03 is stale; C-04–C-06 are open and are listed as residual risk, not results.

## Claim ledger

| ID | Claim | Mechanism | Evidence | Scope / TCB | Status | Limitations | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 | On the failure path, the context is dropped before `RAISE`; a failure does not leave the context installed. | Context is cleared on the failure path before the exception is raised. | `t/131`: 10/10. | Path exercised by `t/131`; PostgreSQL version and environment not supplied. No privileged actors covered. | `tested` | No negative-control/mutation run for `t/131`; environment, commit, and date not supplied. Test result only; not a formal proof. | Not supplied |
| C-02 | The full installcheck suite reports 876/876 on PostgreSQL 14–17. | Project installcheck suite. | Installcheck run: 876/876. | PostgreSQL 14–17; per-major breakdown not supplied. Suite contents and negative cases not enumerated in the supplied facts. | `tested` | The supplied facts do not establish coverage of ASAN, CE-4/CE-7 runtime behavior, or stale-worker rotation; they do not state whether the run followed CE-3; date and commit not supplied. | Not supplied |
| C-03 | ASAN reports 866/866 on a pre-CE-3 revision. | ASAN-instrumented build and test run. | ASAN run: 866/866. | Pre-CE-3 revision; PostgreSQL version and commit not supplied. | `tested` (stale) | Not rerun after CE-3; does not cover the CE-3 change and is not evidence for 1.4.12. No ASAN result for this release. | Pre-CE-3; date and commit not supplied |
| C-04 | Out-of-supported configurations fail closed. | Fail-closed handling for out-of-supported configurations (exact check not supplied). | None supplied. | Out-of-supported configurations; supported/unsupported boundary not supplied. Privileged actors not covered. | `open` | Implementation is stated in the release facts, but no test, analysis, or review artifact was supplied. Do not present as a tested result. | Not supplied |
| C-05 | CE-7 is documented as `PARALLEL RESTRICTED`; runtime behavior of the parallel-worker path is not established. | `PARALLEL RESTRICTED` marking/documentation (exact declaration not supplied). | Documentation/declaration change; artifact path not supplied. | Parallel-worker path. No runtime test. | `open` | Documentation/declaration only. The label does not by itself show that a worker cannot reach the path. | Not supplied |
| C-06 | Secret rotation invalidates a stale worker's context. | Not established in the supplied facts. | None supplied. | Secret rotation followed by a stale worker. | `open` | The supplied facts contain no test evidence for this scenario. Do not claim rotation covers a stale worker; treat it as residual risk. | Not supplied |

## Open claims and residual risk

- **CE-4 fail-closed (C-04): implementation stated; no independent test or analysis artifact supplied.** The supported/unsupported boundary is not supplied. The fail-closed behavior is not a tested result in this note.
- **CE-7 (C-05): documentation/declaration only.** No parallel-worker runtime test was supplied; the `PARALLEL RESTRICTED` label does not establish that the worker path is unreachable.
- **Stale worker after secret rotation (C-06): no test evidence.** Rotation is not shown to invalidate a stale worker's context. Residual risk remains.
- **ASAN (C-03): stale.** The 866/866 result predates CE-3 and was not rerun after CE-3; it does not support memory-safety claims for 1.4.12.
- **`t/131`: pass without a supplied negative control.** The 10/10 result does not by itself show that the test fails when the fix is removed.
- **Full installcheck 876/876: scoped to PostgreSQL 14–17.** The supplied facts do not establish coverage of ASAN, CE-4/CE-7 runtime behavior, or stale-worker rotation; they do not state whether the run followed CE-3; the per-major breakdown, commit, and date are not supplied.
- **CI and upgrade impact: not supplied.** No CI result or upgrade action is claimed.

## Scope and assumptions

- **Version:** rbac 1.4.12.
- **Installcheck:** PostgreSQL 14–17, as reported; per-major counts are not supplied.
- **CE-3:** the path exercised by `t/131`; the supplied facts do not state the test environment, commit, date, PostgreSQL version, or configuration. The 10/10 result is limited to the run reported.
- **CE-4:** out-of-supported configurations as defined by rbac; that definition is not included in the supplied facts.
- **CE-7:** only the `PARALLEL RESTRICTED` documentation/declaration is in scope of the supplied facts. Parallel-worker runtime behavior is not tested.
- **Stale worker after secret rotation:** outside the tested scope; residual risk.
- **Privileged actors and threat model:** not stated in the supplied facts. No claim in this note covers superuser, DBA, deployment admin, secret manager, or operator paths.
- **Assumptions:** none are stated in the supplied facts for cryptographic primitives, clock, network, storage, tenant isolation, or configuration. This note does not assert any.
- **Evidence types:** no formal proof, model checking, static analysis, or independent review is included in the supplied evidence.

## Evidence index

| Ref | Artifact | Command / procedure | Commit | Environment | Date | Result |
| --- | --- | --- | --- | --- | --- | --- |
| E-01 | `t/131` (test file) | Test runner invocation not supplied. | Not supplied | Not supplied | Not supplied | 10/10. |
| E-02 | Full installcheck output | Full installcheck run; exact invocation not supplied. | Not supplied | PostgreSQL 14–17; per-major breakdown not supplied | Not supplied | 876/876. |
| E-03 | ASAN output | ASAN build and test run; exact command not supplied. | Pre-CE-3 revision; SHA not supplied | ASAN build; PostgreSQL version not supplied | Not supplied | 866/866; not rerun after CE-3. |
| E-04 | Not supplied | Not supplied | Not supplied | Out-of-supported configurations | Not supplied | No test evidence for CE-4 fail-closed. |
| E-05 | Documentation/declaration (path not supplied) | Not supplied | Not supplied | Parallel-worker path | Not supplied | CE-7 marked `PARALLEL RESTRICTED`; runtime not tested. |
| E-06 | Not supplied | Not supplied | Not supplied | Secret rotation followed by a stale worker | Not supplied | No test evidence. |

## Evidence freshness

- **Last full test run:** date and commit not supplied. This draft does not assert a release commit.
- **Full installcheck:** 876/876 on PostgreSQL 14–17; date and commit not supplied; whether it followed CE-3 is not stated.
- **CE-3 regression:** `t/131` 10/10; date, commit, and environment not supplied.
- **ASAN:** 866/866 from a pre-CE-3 run; not rerun after CE-3. This result is stale for 1.4.12.
- **Not rerun for this release:** ASAN after CE-3; stale-worker-after-secret-rotation scenario; CE-4 fail-closed behavior; CE-7 parallel-worker runtime.
- **CI:** no result supplied; this note does not claim a CI result.
- **Upgrade impact:** not supplied; this note does not claim an upgrade action or its absence.

## Evidence gaps to close before publication

1. Attach the exact `t/131` command, environment, commit, and date.
2. Attach the installcheck command, per-major results, commit, and date.
3. Rerun ASAN after CE-3, or keep this note free of any ASAN coverage claim for 1.4.12.
4. Add a test or analysis artifact for CE-4 fail-closed, or keep CE-4 as an implementation note with status `open`.
5. Add a parallel-worker runtime test for CE-7, or keep the note limited to the documentation/declaration.
6. Add a stale-worker-after-rotation test, or publish the residual risk as-is.
