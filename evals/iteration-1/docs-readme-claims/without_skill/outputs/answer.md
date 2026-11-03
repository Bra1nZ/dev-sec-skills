# Corrected README Section

## Security testing status

The current test suite reports **876/876 tests passing on PostgreSQL 14, 15, 16, and 17**. This is a point-in-time result for the tested revision; it demonstrates that the covered cases pass and does not by itself establish the absence of security defects.

Negative tests **T-04 through T-11** cover three scenario classes across PostgreSQL 14–17:

- role `Y`;
- role-less sessions;
- cross-tenant writes.

These tests provide regression coverage for those specific cases. They do not constitute a general guarantee of tenant isolation.

Known limitations of the current evidence:

- **AddressSanitizer (ASAN) was not rerun after the CE-3 fix.** The current revision therefore has no post-fix ASAN result.
- **Stale-worker behavior after `rotate_session_secret()` is untested.** No claim is made about worker behavior across secret rotation.
- **Superusers and DBAs are outside the threat model.** The extension's controls are not intended to constrain accounts with those privileges.
- **No FSTEC 76 audit has been performed.** No compliance with FSTEC 76 is claimed.

A security claim should only be added here once it is backed by a reproducible test result or audit report that names the revision, environment, and scope.

---

# Claim Ledger

| ID | Original claim | Verdict | Evidence | Corrected wording / disposition |
|----|----------------|---------|----------|---------------------------------|
| C1 | "The extension is secure." | Unsupported | No security proof, audit, or exhaustive analysis is cited. Passing tests cannot establish this. | Removed. Replaced with the tested scope and explicit limitations. |
| C2 | "Fully tested." | Contradicted | ASAN was not rerun after the CE-3 fix; stale-worker behavior after `rotate_session_secret()` is untested. | Replaced with "876/876 tests passing" plus a named list of untested areas. |
| C3 | "All 876 tests pass." | Supported (scoped) | 876/876 passed on PostgreSQL 14–17. | Retained as "876/876 tests passing on PostgreSQL 14, 15, 16, and 17," explicitly labeled a point-in-time result. |
| C4 | "It guarantees tenant isolation." | Partially supported / overstated | Negative tests T-04–T-11 cover role `Y`, role-less sessions, and cross-tenant writes on PostgreSQL 14–17 only; superusers and DBAs are outside the threat model. | Replaced with "regression coverage for those specific cases"; no guarantee asserted. |
| C5 | "It is compliant with FSTEC 76." | Unsupported | No FSTEC audit was performed. | Removed. Replaced with "No FSTEC 76 audit has been performed. No compliance with FSTEC 76 is claimed." |

## Evidence still required to strengthen these claims

| Claim to be earned | Evidence required |
|--------------------|-------------------|
| ASAN-clean current build | ASAN run on the revision containing the CE-3 fix, with command line and results recorded. |
| Stale-worker behavior across secret rotation | Test covering `rotate_session_secret()` with live/stale workers, including expected and observed behavior. |
| Broader tenant-isolation assurance | Additional negative tests beyond T-04–T-11, including failure-mode and concurrency cases, with documented threat model. |
| FSTEC 76 compliance | Formal audit against FSTEC 76 requirements by an qualified assessor, with report and scope. |
| Reproducible test result | Test report tied to a specific commit, PostgreSQL build, and date. |
