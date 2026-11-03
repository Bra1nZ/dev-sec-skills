# evidence-first-docs

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: agent skill](https://img.shields.io/badge/format-SKILL.md-orange)](SKILL.md)
[![Focus: evidence before claims](https://img.shields.io/badge/focus-evidence%20before%20claims-2ea44f)](SKILL.md)

An agent skill for writing and reviewing technical documentation: READMEs,
architecture docs, ADRs, API contracts, security/compliance sections, release
notes, audit packs, and handoff notes.

It is for text that promises more than was verified. "The system is secure",
"everything is tested", "compliant with the standard", "guarantees integrity"
are not claims until a mechanism, evidence, scope, and an honest status sit
next to them.

## The core idea

Documentation is not a story about the system. It is a **claim ledger**. Every
material statement must be traceable to a mechanism and to evidence, with the
limits stated in the same place as the claim.

Every claim has four required fields:

1. **Mechanism** — what in the system is supposed to make the claim true.
2. **Evidence** — proof, model, test, analysis report, trace, benchmark, or
   review record.
3. **Scope** — where the claim applies and what is outside the trust boundary.
4. **Status** — the strongest honest label the evidence supports.

If one is missing, there is no claim: there is an intent, a plan, or an open
question. They may stay in the document, but they must not be presented as a
result.

## Statuses

| Status | Meaning |
| --- | --- |
| `proven` | Machine-checked proof of the property under explicit assumptions and TCB |
| `model-checked` | Exhaustive or bounded exploration of a model; bound and model-to-code gap stated |
| `tested` | Executed tests that attempted the violation, with environment and result |
| `static-refinement` | Static analysis or refinement check; tool, rules, and unresolved findings stated |
| `reviewed` | Human review only; no executable or formal evidence |
| `open` | The claim exists but evidence does not; it is a risk, not a result |

Lowering a status is not a failure. Inflating one is.

## What is inside

- `SKILL.md` — workflow, claim ledger, statuses, scope/TCB, evidence strength,
  review checklist, anti-patterns.
- [`references/banned-words.md`](references/banned-words.md) — loaded words in
  English and Russian, normative `MUST/SHOULD/MAY`, replacements for vague
  quantifiers.
- [`references/evidence-template.md`](references/evidence-template.md) —
  templates for the claim ledger, evidence index, release note, review record,
  and negative-result record.

## When to use

- Before publishing a README or architecture document.
- Before release notes that must separate supported claims from open risk.
- Before an audit or certification that needs an evidence pack.
- When reviewing security/compliance text: "secure", "compliant", "certified",
  "guaranteed" without scope.
- After an incident: update the claim ledger and add a negative result, not
  only a polished postmortem.

## Example

Bad:

> The system is secure and fully tested. All tests pass.

Good:

> Role Y cannot write table T on PostgreSQL 14–17 through the HTTP, batch, or
> admin API (tests T-04..T-11, status `tested`; superuser and DBA are outside
> the model). Known limitation: stale-worker behavior after secret rotation is
> not verified (`open`).

## Install

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
```

The skill activates when a document states that something is secure, correct,
complete, verified, tested, certified, compliant, or guaranteed; when
documentation needs a review for unsupported claims; and when prose must
survive an auditor or an incident.

## Related skills

- [`negative-test-first`](../negative-test-first/SKILL.md) supplies evidence
  for `tested` and `open` statuses.
- [`invariant-first-code`](../invariant-first-code/SKILL.md) supplies the
  mechanism and enforcement point for code claims.
- The standards crosswalk is in
  [`references/standards-map.md`](../../references/standards-map.md).

## License

MIT — see [LICENSE](LICENSE). Third-party standards keep their own
licenses.
