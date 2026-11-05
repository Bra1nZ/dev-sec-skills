# Standards Map

This is a design crosswalk, not a certification or an audit. It shows which
skill rules have a recognizable analogue in the standards, so a team can
reuse its existing evidence instead of inventing a parallel compliance
universe.

Use it in three steps:

1. Find the skill rule you are applying.
2. Read the international analogue for the engineering method.
3. Read the FSTEC/GOST column for the evidence and documentation a Russian
   review or certification may expect.

Clause-level mapping must be checked against the official text of the
version you are actually subject to. This file deliberately maps principles,
not clause numbers.

## Sources

| Source | Scope | Status |
| --- | --- | --- |
| ФСТЭК России, приказ № 55 от 03.04.2018 | Certification of security tools; evidence pack, change control, traceability | Russian regulatory process |
| ФСТЭК России, приказ № 76 от 02.06.2020 | Trust levels; security model, secure development, testing, vulnerability handling, support | Russian requirements |
| ФСТЭК России, приказ № 64 от 14.04.2023 | Security requirements for DBMS | Russian domain checklist |
| ГОСТ Р 56939-2024 | Secure software development lifecycle | Russian national standard |
| ГОСТ Р 71207-2024 | Static analysis; critical errors, triage, FP/FN, qualification | Russian national standard |
| NIST SP 800-218 | Secure Software Development Framework (SSDF) | Public |
| NIST SP 800-160 Vol. 1 Rev. 1 | Security engineering; lifecycle, trustworthiness | Public |
| NIST SP 800-115 | Technical security testing and assessment | Public |
| OWASP ASVS 5.0 | Application security verification requirements | CC BY-SA 4.0 |
| ISO/IEC/IEEE 29148 | Requirements engineering | Paywalled |
| ISO/IEC/IEEE 42010 | Architecture description | Paywalled |
| ISO/IEC/IEEE 29119 | Software testing | Paywalled |
| ISO/IEC 25010 | Product quality model | Paywalled |
| ISO/IEC 15408 (Common Criteria) | Security evaluation; protection profiles, assurance levels | Paywalled |
| CWE / SARIF | Weakness taxonomy / analysis-result exchange | Public |
| SLSA / SPDX / CycloneDX | Build provenance / SBOM formats | Public |
| in-toto | Supply-chain layout and attestations | Public |
| SCITT / Rekor | Transparency logs; signed, append-only statements | Public specifications |
| OMG SACM / GSN | Assurance-case structure and argument notation | Public / community |
| OSCAL (NIST) | Machine-readable control and assessment descriptions | Public |
| RFC 2119 / RFC 8174 | Normative requirement keywords | Public |
| Diátaxis; Google and Microsoft style guides | Documentation structure and controlled language | Public |

See `standards/SOURCES.md` for URLs, licenses, and local copies.

## Crosswalk

### Testing and evidence

| Skill rule | FSTEC / GOST | International analogue | Action |
| --- | --- | --- | --- |
| Claim list with stable IDs | ФСТЭК 55 (evidence pack), ФСТЭК 76 (design and test docs), ГОСТ 56939 (secure SDLC) | ISO/IEC/IEEE 29148; NIST SSDF PW.1, PS.1 | Keep `claim -> mechanism -> test -> result` in one ledger |
| Negative test for every claim | ФСТЭК 76 (test coverage, NDV), ФСТЭК 64 (access-control checks), ГОСТ 56939 | ISO/IEC/IEEE 29119; NIST SP 800-115; OWASP ASVS/WSTG | Name the violation attempt; verify it fails when the guard is removed |
| Boundary and class enumeration | ФСТЭК 76 (test completeness), ГОСТ 56939 | ISO/IEC/IEEE 29119; CWE-20, CWE-1284 | Test empty, one, many, limit, limit+1, wrong type/order |
| Failure side-effect check | ФСТЭК 76 (integrity), ФСТЭК 64 (data integrity) | OWASP ASVS V5/V7; CWE-460, CWE-636 | After refusal, assert no partial write, no state change |
| Refusal classification | ФСТЭК 76 (error handling) | NIST SP 800-115; CWE-391, CWE-755 | Assert code, reason, and layer; never pass on any exception |
| Platform matrix and honest branching | ФСТЭК 76 (supported environment), ФСТЭК 64 (DBMS environment) | ISO/IEC/IEEE 29119; OWASP ASVS | Record what passed where; label platform defense in depth |
| Migration and regression negatives | ФСТЭК 76 (change control), ГОСТ 56939 | NIST SSDF PW.6; ISO/IEC/IEEE 29119 | Rerun negatives on migrated live data |
| Performance baseline | ФСТЭК 64 (availability/performance), ФСТЭК 76 (nonfunctional tests) | ISO/IEC 25010; NIST SP 800-115 | Interleaved A/B, server-side medians, stated validity conditions |
| Static analysis evidence | ГОСТ 71207; ГОСТ 56939 | CWE; SARIF; NIST SSDF PW.7/PW.8 | Record tool, rules, findings, triage, FP/FN, repeatability |
| Verify the verifier | ГОСТ 71207 (qualification tests), ГОСТ 56939 (test quality) | NIST SP 800-115; mutation testing | Mutation/no-op test; artifact presence is not evidence |
| Configuration and change control | ФСТЭК 55 (certification changes), ФСТЭК 76 (config management), ГОСТ 56939 | NIST SSDF PO.3/PW.6; ISO/IEC/IEEE 29119 | Record baseline, change approval, affected claims, rerun evidence |
| Vulnerability and NDV handling | ФСТЭК 76 (vulnerability/NDV), ГОСТ 56939 (defect management) | NIST SSDF RV.1; CWE | Triage, fix, regression test, disclosure record |
| Covert/hidden channels | ФСТЭК 76 (hidden channels) | ISO/IEC 15408 | Analyze only when the claim requires it; state method and bound |
| Support and update lifecycle | ФСТЭК 76 (support/updates), ГОСТ 56939 (delivery) | NIST SSDF RV.2/PS.3; SLSA | Define support window, update path, provenance, end-of-life |

### Documentation and claims

| Skill rule | FSTEC / GOST | International analogue | Action |
| --- | --- | --- | --- |
| Every material claim has mechanism, evidence, scope, status | ФСТЭК 55 (evidence), ФСТЭК 76 (design docs), ГОСТ 56939 (SDLC docs) | ISO/IEC/IEEE 29148; ISO/IEC/IEEE 42010; NIST SSDF PS.1 | Maintain the claim ledger; link artifacts, not tool names |
| Falsifiable requirements | ФСТЭК 76 (security requirements), ГОСТ 56939 (requirements phase) | ISO/IEC/IEEE 29148; RFC 2119/8174 | Use `MUST`/`SHOULD`/`MAY` deliberately; define terms once |
| Architecture description and trust boundary | ФСТЭК 76 (security architecture), ФСТЭК 64 (DBMS architecture) | ISO/IEC/IEEE 42010; NIST SP 800-160 | State components, interfaces, TCB, excluded actors |
| Threat model and attack surface | ФСТЭК 76 (security model, attack surface), ФСТЭК 64 (access control) | NIST SP 800-160; OWASP ASVS V1; CWE | Name assets, actors, entry points, abuse cases |
| Traceability to requirements | ФСТЭК 55 (certification evidence), ФСТЭК 76 (design/test docs) | ISO/IEC/IEEE 29148; NIST SSDF PW.1 | One row per claim; no orphan requirement or test |
| Residual risk and release decision | ГОСТ 56939 (release with residual risk), ФСТЭК 76 (support/updates) | NIST SSDF RV.1/RV.2; ISO/IEC/IEEE 29119 | Release note lists open claims, not "all tests pass" |
| Controlled language and banned words | ФСТЭК 55/76 (evidence quality) | RFC 2119/8174; Google/Microsoft style guides; Diátaxis | Remove unqualified absolutes; keep caveats next to claims |
| Documentation structure | ФСТЭК 76 (documentation set) | Diátaxis; ISO/IEC/IEEE 42010 | Separate tutorial, how-to, reference, explanation; keep evidence index |
| Negative results and known failures | ФСТЭК 76 (vulnerability handling), ГОСТ 56939 (defect management) | NIST SSDF RV.1; CWE | Keep negative-result records; do not filter failures |

### Code and invariants

| Skill rule | FSTEC / GOST | International analogue | Action |
| --- | --- | --- | --- |
| Explicit invariant map | ФСТЭК 76 (security model), ФСТЭК 64 (DBMS requirements) | NIST SP 800-160; ISO/IEC 25010 | One invariant per row; enforcement point and failure mode |
| Default deny / fail closed | ФСТЭК 76 (no bypass), ФСТЭК 64 (access control) | OWASP ASVS V4/V8; CWE-285, CWE-862, CWE-863, CWE-636 | Deny on error, timeout, missing policy, unknown role |
| No bypass through alternative paths | ФСТЭК 76 (security function bypass), ФСТЭК 64 (access control) | OWASP ASVS V4/V8; CWE-639, CWE-862 | Test every entry point, batch/import/admin/migration |
| Object-level authorization | ФСТЭК 64 (DAC/RBAC), ФСТЭК 76 (access control) | OWASP ASVS V4; CWE-639 | Test neighboring tenant, owner, role-less, expired |
| Data integrity and transactions | ФСТЭК 64 (integrity), ФСТЭК 76 (data protection) | OWASP ASVS V5/V7; CWE-20, CWE-89, CWE-502 | Constraints, atomic refusal, idempotency, restore drill |
| Concurrency and stale workers | ФСТЭК 64 (availability/integrity) | OWASP ASVS V11; ISO/IEC 25010 | Locks, fencing tokens, duplicate delivery, retry storms |
| Audit trail integrity | ФСТЭК 64 (audit), ФСТЭК 76 (registration) | OWASP ASVS V7; CWE-117, CWE-532 | One write channel; actor cannot edit/delete own trail |
| Secrets and cryptography | ФСТЭК 64 (authentication), ФСТЭК 76 (cryptographic protection) | OWASP ASVS V6; CWE-798, CWE-522 | Secret store, rotation window, no logs, stale-credential test |
| Memory clearing and lifecycle | ФСТЭК 64 (memory clearing), ФСТЭК 76 (lifecycle) | OWASP ASVS V6/V8; CWE-226, CWE-316 | Wipe sensitive buffers; cleanup on every exit path |
| Supply chain and build | ГОСТ 56939 (secure build/composition) | NIST SSDF PS.2/PS.3; SLSA; SPDX/CycloneDX | Pin inputs, SBOM, provenance, secret scanning |
| Platform contract | ФСТЭК 76 (supported environment), ФСТЭК 64 (DBMS environment) | NIST SP 800-160; OWASP ASVS | Declare versions/privileges; test each supported platform |

### Conveyor artifacts (`spec/`)

The crosswalk below maps the phase-0 artifacts to standards. It is a design
mapping: none of these rows is evidence that the conveyor exists or that a
verdict is trustworthy.

| Conveyor artifact | FSTEC / GOST | International analogue | Action and status |
| --- | --- | --- | --- |
| Verdict registry: append-only, hash-chained, externally anchored | ФСТЭК 55 (evidence pack, change control), ГОСТ 56939 (release evidence) | in-toto attestations; SLSA provenance; SCITT / Rekor transparency log; NIST SSDF PS.2/PS.3 | Name the anchor before claiming integrity; record commit, extractor hash, verifier versions, model hash, result. Status `open` (C-13) |
| Cell taxonomy bounded to failure classes | ФСТЭК 76 (security model, test coverage), ГОСТ 56939 (requirements and testing) | NIST SP 800-160; ISO/IEC/IEEE 29119; CWE | Map cells to CWE classes where one exists; an `unroutable` finding is a coverage gap, not a new cell. Status `open` (C-11) |
| Provenance as taint, not trust | ФСТЭК 76 (development environment, configuration management) | SLSA provenance; in-toto layout | Provenance routes checks; it does not weaken or replace them. A provenance label is not a safety statement |
| Guard grammar and extraction completeness gate | ФСТЭК 76 (no bypass, security model), ГОСТ 56939 (static analysis, testing) | ISO/IEC/IEEE 29119; NIST SP 800-115; CWE-285/CWE-862/CWE-863 | State the expressible subset and exclude concurrency, transactions, and supply chain. Extraction soundness is `open` until the mutation set passes (C-09) |
| Self-mutation with an external judge | ГОСТ 71207 (qualification tests, repeatability), ГОСТ 56939 (test quality) | Mutation testing; NIST SP 800-115 | The judge must be outside the conveyor. A held-out suite alone is not acceptance criteria (C-10) |
| Machine-readable assurance claims | ФСТЭК 55/76 (evidence and design docs) | OMG SACM / GSN; OSCAL | Export the ledger to an assurance-case or OSCAL form; the export does not turn an `open` claim into evidence |

SACM/GSN describes the structure of an argument; it does not execute a merge
gate. OSCAL describes controls and assessment results; it does not verify code.
Neither substitutes for a verdict produced by a mechanism.

### Russian-specific notes

| Source | What it adds to the skills | What it does not justify |
| --- | --- | --- |
| ФСТЭК 55 | Certification process: evidence pack, change control, traceability, test records | A claim that the product is "certified" without a scoped certificate |
| ФСТЭК 76 | Trust levels, security model, no bypass, interfaces/errors, config management, secure development docs, test coverage, vulnerability/NDV handling, hidden channels, support | Formal proof as a universal requirement; level 4 is a specific claim, not a default |
| ФСТЭК 64 | DBMS checklist: DAC+RBAC, authentication, integrity, audit, backup/restore, availability, memory clearing, performance, software environment | A general web-app checklist; apply it only to DBMS claims |
| ГОСТ 56939 | Secure SDLC: requirements, configuration, defects, architecture, threat model/attack surface, coding rules, review, static/dynamic/fuzz, secure build, secrets, composition, testing, release with residual risk, delivery | A guarantee that every phase was performed; evidence is still required |
| ГОСТ 71207 | Static analysis: critical errors, triage, FP/FN, qualification tests, CWE/SARIF, repeatability | That FP/FN ≤ 50% is a quality target; it is a certification floor |
| ISO/IEC 15408 | Common Criteria: protection profiles, assurance levels, covert channels | A claim that a product is "certified" without a valid certificate and scope |

## Compliance honesty

A mapping is not an audit. A standard's name is not evidence. If a document
needs to say "compliant" or "certified", it must name:

- the standard and version;
- the certification body or auditor;
- the scope (product, version, configuration, site);
- the date and validity period;
- the exclusions and open findings.

Otherwise write "mapped to" or "designed to support", and link the gap list.
