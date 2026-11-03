---
name: evidence-first-docs
description: >
  Evidence-first writing for technical documentation: READMEs, architecture
  and design docs, ADRs, API contracts, security and compliance claims,
  release notes, audit packs, and handoff notes. Use whenever a document
  states that something is secure, correct, complete, verified, tested,
  certified, compliant, or guaranteed; whenever you review documentation for
  unsupported claims; and whenever prose must survive a reviewer, an auditor,
  or an incident. Every material claim gets a mechanism, evidence, scope, and
  status.
---

# Evidence-First Docs

Documentation is not a story about the system. It is a claim ledger: each
material statement must be traceable to a mechanism and to evidence, with the
limits stated in the same place as the claim.

A confident sentence is cheap. The job is to make the reader able to tell what
was proven, what was tested, what was only reviewed, and what remains open.

## The core rule

Every material claim carries four things:

1. **Mechanism** — what in the system is supposed to make the claim true.
2. **Evidence** — the proof artifact: proof, model, test, analysis report,
   trace, benchmark, or review record.
3. **Scope** — where the claim applies and what is outside the trust boundary.
4. **Status** — the strongest honest label the evidence supports.

If one of the four is missing, the claim is not ready. Rewrite it as a design
intent, a plan, or an open question — do not dress it as a result.

## Claim ledger

Maintain a table, in the document or in a linked evidence file:

| ID | Claim | Mechanism | Evidence | Scope / TCB | Status | Limitations | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-01 | Only role X can write table T | Permission check + DB policy | Negative tests T-04..T-11 | PostgreSQL 14–17; role Y, role-less session | tested | Superuser and DBA are outside the threat model | 2026-11-02 |

Rules:

- One row per claim, not one row per document.
- Claims must be falsifiable. "The system is secure" is not a claim; "role Y
  cannot write T through any supported entry point" is.
- Link the artifact, not just the tool name. "SARIF" is a format; the report
  path and the reviewed rule set are evidence.
- Update `Last verified` when the artifact is rerun; stale evidence is a
  finding, not a formality.
- Keep negative results. "We tried to break it and failed because of X" is
  evidence; hiding it produces a false sense of coverage.

## Status ladder

Use the strongest label the evidence supports, never a stronger one:

| Status | Meaning |
| --- | --- |
| `proven` | Machine-checked proof of the stated property, with assumptions and TCB declared |
| `model-checked` | Exhaustive or bounded exploration of a model; state the bound and model-to-code gap |
| `tested` | Executed tests that attempt the violation, with environment and result recorded |
| `static-refinement` | Static analysis or refinement check; state tool, rules, and unresolved findings |
| `reviewed` | Human review only; no executable or formal evidence |
| `open` | Claim exists but evidence does not; it is a risk, not a result |

A lower status is not a failure. An inflated status is.

Do not write `verified`, `proven`, `correct`, `secure`, `safe`, `complete`,
`guaranteed`, `certified`, or `compliant` without an adjacent status and
scope. If the word would survive without the evidence, delete the word.

## Evidence strength

Prefer evidence that can fail for the right reason:

1. Formal proof of the stated property under explicit assumptions.
2. Exhaustive model checking within a stated bound.
3. Property-based or fuzz testing with a recorded corpus and oracle.
4. Targeted negative tests that fail when the mechanism is removed.
5. Static analysis with a reviewed rule set and triaged findings.
6. Code review with named reviewers and a checklist.
7. Assertion or anecdote.

The hierarchy is not absolute: a targeted test can be stronger than a
misapplied proof. Match the evidence to the claim. A proof of a model that
does not refine the code does not prove the code. A test that passes because
the platform refused first does not prove your guard.

## Scope and trust boundary

State the boundary next to the claim, not in a distant appendix:

- Versions and platforms covered.
- Privileged actors excluded: superuser, DBA, deployment admin, secret
  manager, build system, operator.
- Assumptions: cryptographic primitives, clock, network, storage, tenant
  isolation, configuration.
- What is modeled symbolically and what is executed for real.
- What is out of scope and why.

An unqualified claim is a claim about everything, which is almost always
false. "Secure against role Y on PostgreSQL 14–17 with the documented
configuration; DBA is outside the model" is honest and useful.

## Workflow

1. **Inventory claims.** Read the text and mark every sentence that asserts a
   property, result, guarantee, or compliance status.
2. **Classify each claim.** Is it a design intent, a requirement, an
   implementation fact, a test result, a formal result, or a release claim?
3. **Assign an ID and a status.** Add mechanism, evidence, scope, limitations,
   and `Last verified`.
4. **Test the claim against the artifact.** Open the report, rerun the command,
   or ask for the missing artifact. Do not accept a filename as evidence.
5. **Rewrite unsupported claims.** Convert them to "design intent", "planned",
   "not yet verified", or an open question. Preserve the ambition; remove the
   false certainty.
6. **Check the negatives.** For every security or correctness claim, name the
   test or analysis that tried to violate it. If there is none, mark the claim
   `open`.
7. **Review the language.** Remove banned words, vague quantifiers, and
   unqualified absolutes. See `references/banned-words.md`.
8. **Freeze the evidence.** Record the command, commit, environment, date, and
   artifact path so a reviewer can reproduce the result.
9. **Gate the release.** A release note may claim only what the ledger
   supports. List residual risk and open claims explicitly.

## Review checklist

- Every material claim has an ID, mechanism, evidence, scope, status, and
  limitations.
- Every `tested` claim names a test that can fail when the mechanism is
  removed.
- Every `model-checked` claim states the bound and the model-to-code gap.
- Every `proven` claim states assumptions and TCB.
- Negative results and known failures are present, not filtered out.
- Dates and versions are current; stale evidence is marked stale.
- Privileged actors and out-of-scope paths are named.
- No banned word appears without adjacent evidence and scope.
- The README, architecture doc, API contract, and release note do not
  contradict each other.
- A reader can reproduce the evidence from the document alone.

## Anti-patterns

1. **Aspirational present tense.** "The system enforces..." when it is a plan.
2. **Evidence by filename.** "See report.pdf" with no result, scope, or date.
3. **Tool name as proof.** "Verified with static analysis" without rules,
   findings, and triage.
4. **Scope laundering.** A narrow test result presented as a product-wide
   guarantee.
5. **Green-suite absolutism.** "All tests pass" without saying which tests,
   on which platforms, and what they attempted to violate.
6. **Compliance cosplay.** A standard's name used as a certificate; a mapping
   is not an audit.
7. **Buried limitations.** The caveat exists but is far from the claim.
8. **Stale certainty.** A result from an old commit presented as current.
9. **No negative evidence.** Only successes are documented; failures and
   refusals disappear.

## Output shape

When asked to write or review a technical document, produce:

1. A short **claim summary** with counts by status.
2. The **claim ledger** (inline or linked).
3. **Open claims and residual risk**, explicitly separated from results.
4. **Scope and assumptions**, next to the claims they constrain.
5. **Evidence index** with paths, commands, dates, and versions.

Use `references/evidence-template.md` for the ledger and release-note shape.
Use `references/banned-words.md` before publishing. If the repository includes
a standards crosswalk, it lives at `references/standards-map.md`; the skill
itself does not depend on a standard.

Scale the output to the document. A short release note needs a compact claim
table and a short residual-risk section, not a full audit pack. A certification
evidence file needs the full ledger, evidence index, and scope. Do not confuse
thoroughness with length; every row must carry information a reader needs.
