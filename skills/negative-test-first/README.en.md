# negative-test-first

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: agent skill](https://img.shields.io/badge/format-SKILL.md-orange)](SKILL.md)
[![Discipline: negative test first](https://img.shields.io/badge/discipline-negative--test--first-2ea44f)](SKILL.md)

An agent skill for the general testing discipline of any product with claims
that must hold: business rules ("a withdrawal cannot exceed the balance"),
data invariants ("balance equals the sum of movements"), persistence ("data
survives a restart"), concurrency ("no double spending"), API contracts,
access control, and audit — everything where "the feature works" proves
nothing and only "the violation fails" does.

The skill grew out of practice: building a PostgreSQL access-control extension
where every protection mechanism must carry a negative test, and every escaped
defect becomes a named lesson that lives in code comments and in the tests.

## The core idea

A requirement is covered only when a test shows that **violating it does not
work**. A suite that checks only happy paths proves nothing about the rule. For
every claim — "you cannot withdraw more than the balance", "only role X may
write table T", "data survives a restart" — there must be a test that tried to
violate it: at the boundary, one past the boundary, in parallel, through an
alternative path — and failed.

The usual order is reversed: positives first, negatives "if time permits".
Here the negative is written first; the positive is the cheap half. Security
is not a separate topic but the sharpest case of the same discipline.

## What is inside

`SKILL.md` is compressed to the working minimum: the core rule, a
"claim -> required negative" table, a nine-step workflow, patterns,
anti-patterns, and a security section. The motivation and history live in this
README so they do not consume the agent's context.

Key mechanics:

- every requirement pairs with a negative test, and the claim list becomes the
  coverage index;
- input classes are enumerated and tested individually: empty, one, many, at
  the limit, past the limit;
- after an expected failure, assert the world did not change;
- failures are classified by **who** failed — your code, the platform, the
  driver;
- platform branching is honest: "our check is defense in depth" instead of a
  green pass for nothing;
- evidence is checked in two channels: what dies with the transaction and what
  survives it;
- negative tests rerun after a migration on live data;
- performance thresholds come from an A/B baseline;
- the test is checked for its ability to fail: mutation/no-op, not the presence
  of a file.

## Install

The skill is agent-neutral — a `SKILL.md` with principles and patterns.

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/negative-test-first ~/.config/opencode/skills/
```

For agents that read skills elsewhere, put the directory where the agent looks
for skills. It activates when the task involves designing a test plan for a
feature or a product, writing tests for business rules or invariants, reviewing
negative-case coverage, classifying failures, or setting performance baselines.

## Related skills

- [`invariant-first-code`](../invariant-first-code/SKILL.md) names the
  invariants and enforcement points to violate.
- [`evidence-first-docs`](../evidence-first-docs/SKILL.md) records the result,
  scope, and status of the verification.
- The standards crosswalk is in
  [`references/standards-map.md`](../../references/standards-map.md).

## License

MIT — see [LICENSE](LICENSE).
