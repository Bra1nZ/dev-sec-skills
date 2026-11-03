# Field Notes

Why these skills look the way they do. This is the design rationale, not a
standard and not a claim about any product.

## The failure mode

Agents produce three things very well:

1. A plausible implementation.
2. A positive test that exercises the happy path.
3. A confident paragraph explaining why it is safe.

The gap is between (2) and (3). A positive test proves that the code can do
the requested thing. It does not prove that the code refuses the unrequested
thing. A confident paragraph does not close the gap; it hides it.

The skills attack the gap from three sides:

- `invariant-first-code` makes the property explicit and puts enforcement in
  one place.
- `negative-test-first` attacks that enforcement until it either holds or
  breaks.
- `evidence-first-docs` records what survived, with scope and status.

## Lessons from the Russian standards

### ФСТЭК 76

The useful engineering core is not the paperwork. It is the insistence that a
security function cannot be bypassed, that interfaces and errors are part of
the security surface, that configuration is managed, and that testing must
cover the declared requirements. The trust level is a scope statement, not a
badge.

What the skill deliberately does not do: turn formal proof into a universal
requirement. Formal methods are expensive and only meaningful when the model,
assumptions, and TCB are stated. A proof of the wrong model is worse than a
test because it looks stronger.

### ФСТЭК 64

A DBMS checklist is a good reminder that "application security" is not the
whole product. Access control, authentication, integrity, audit, backup,
availability, memory clearing, performance, and the software environment are
separate claims with separate evidence. The skill treats them as separate
invariants, not as one "database is secure" sentence.

### ГОСТ 56939-2024

The lifecycle view is the antidote to release-day optimism. Requirements,
configuration, defect management, architecture, threat model, coding rules,
review, static/dynamic/fuzz analysis, secure build, secrets, composition,
testing, release with residual risk, and delivery are all evidence-producing
activities. A phase that ran is not evidence; an artifact with a result is.

### ГОСТ 71207-2024

Static analysis is useful only when the rule set, findings, triage, false
positives, false negatives, and repeatability are recorded. "The scanner
passed" is not a claim. The FP/FN ≤ 50% figure is a certification floor, not
a quality target; a team that aims for it is aiming for the minimum.

### ФСТЭК 55

Certification is a process with a scope, a body, a date, and a set of
evidence. It is not an adjective. The skill's documentation rules therefore
separate "mapped to" from "certified" and require the certificate's scope
next to the word.

## Design decisions

- **One core, many standards.** The skills are standard-agnostic. The crosswalk
  is a separate file so a team can use the discipline without pretending to
  comply with a standard it has not been audited against.
- **No language annexes.** A rule that only works for Python or PostgreSQL is
  a pattern, not a principle. Examples may be concrete; the rule must be
  portable.
- **Statuses, not adjectives.** `tested`, `model-checked`, `proven`, and
  `open` are more useful than "robust" and "secure" because they can be
  checked.
- **Negative results are evidence.** A failed attempt to break a rule is
  valuable. Deleting it when the happy path turns green destroys the record
  of what was actually covered.
- **Artifact presence is not evidence.** A test file, a report, or a PDF can
  exist without proving anything. The skill asks for the result, the scope,
  and the ability to reproduce.
- **Verify the verifier.** A test that cannot fail is worse than no test
  because it creates false confidence. Mutation, no-op injection, or removing
  the guard is part of the discipline.

## Open questions

- How much of the claim ledger can be generated from code annotations and CI
  artifacts instead of maintained by hand?
- Which static-analysis results can be mapped to invariants automatically?
- How should the skills handle multi-tenant and supply-chain claims where the
  trust boundary crosses organizational lines?
- What is the smallest eval set that shows the skills actually change agent
  behavior rather than adding prose?

These are roadmap questions, not claims. They stay `open` until evidence
exists.
