# Dev-Sec Skills: Evidence Before Claims

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-orange)](skills/negative-test-first/SKILL.md)
[![Languages: RU / EN](https://img.shields.io/badge/docs-RU%20%2F%20EN-2ea44f)](README.md)

Agent skills for teams that need more than a green test and a confident
sentence. One working principle in three planes: **a claim exists only with
evidence, scope, and an honest status.**

The skills are not tied to a language, framework, or standard. They describe
how an agent should reason and what it should check; the references connect
those rules to international and Russian standards.

## Why this exists

Agents write positive tests well and convincing READMEs even better. They
check that code does what was asked and almost never that code refuses what
was not. The result is a green suite that proves nothing about the rule, and a
document that promises more than was verified.

These skills invert the question:

- not "does the feature work?" but "which test tried to violate it?";
- not "is the system secure?" but "who exactly failed to get through, under
  which threat model?";
- not "is everything tested?" but "which claims are still `open`, and who
  admits it?".

## The three skills

| Skill | Use when | Main output |
| --- | --- | --- |
| [`negative-test-first`](skills/negative-test-first/SKILL.md) | Test planning, coverage review, "is it done?", release gate | Every requirement paired with a test that attempts to violate it |
| [`evidence-first-docs`](skills/evidence-first-docs/SKILL.md) | README, architecture, ADR, API contracts, security/compliance claims, release notes, audit packs | Claim ledger: mechanism, evidence, scope, status, limitations |
| [`invariant-first-code`](skills/invariant-first-code/SKILL.md) | Auth, permissions, data, transactions, migrations, concurrency, APIs, secrets, supply chain | Invariant, enforcement point, fail-closed behavior, negative check |

They compose:

1. `invariant-first-code` names what must always hold.
2. `negative-test-first` tries to break it.
3. `evidence-first-docs` records what was actually proven, where, and with
   which limits.

## Shared principles

- **Claim, not mood.** "Secure" and "correct" are not claims. A claim must be
  falsifiable.
- **Negative first.** The positive test is the cheap half. Coverage starts
  with an attempt to violate.
- **Scope next to the claim.** Versions, platforms, privileged actors, and
  exclusions belong where the promise is made.
- **Status, not belief.** `proven`, `model-checked`, `tested`,
  `static-refinement`, `reviewed`, and `open` are different things.
- **An artifact is not evidence.** A report, test, or PDF does not prove
  anything without a result, a scope, and reproducibility.
- **Standard-agnostic core.** The skills do not name standards. The crosswalk
  does.

## Standards

The core draws on practices found in NIST SSDF, NIST SP 800-160, OWASP ASVS,
ISO/IEC/IEEE 29148/42010/29119, ISO/IEC 25010, CWE/SARIF, SLSA,
SPDX/CycloneDX, RFC 2119/8174, and Diátaxis.

Russian requirements — FSTEC 55, 76, 64 and GOST R 56939-2024 / 71207-2024 —
are not dissolved into the core. They live in
[`references/standards-map.md`](references/standards-map.md) with international
analogues. It is a **crosswalk, not a certification or an audit**: a mapping
table cannot declare compliance.

Downloaded freely available documents and links to paywalled ISO standards are
in [`references/standards/SOURCES.md`](references/standards/SOURCES.md).

## Concept: the verification conveyor

The [`spec/`](spec/README.md) directory is the knowledge layer of a system that
assembles these skills into a conveyor: default deny at merge, provenance as
taint, a cell taxonomy instead of an accumulating pile of lessons, a verdict
registry, and an explicit promise boundary for L2.

- [`spec/conveyor/CONCEPT.md`](spec/conveyor/CONCEPT.md) — the concept with
  claims C-01…C-16 (Russian source of truth); English derivative:
  [`CONCEPT.en.md`](spec/conveyor/CONCEPT.en.md).
- [`spec/conveyor/cell-registry.schema.json`](spec/conveyor/cell-registry.schema.json)
  — the machine-readable cell.
- [`spec/conveyor/cells.seed.yaml`](spec/conveyor/cells.seed.yaml) — 12 seed
  cells from the six invariant categories, all `open`.
- [`spec/conveyor/guard-grammar.md`](spec/conveyor/guard-grammar.md) — what L2
  can and cannot check; English derivative:
  [`guard-grammar.en.md`](spec/conveyor/guard-grammar.en.md).

Phase 0 status: document and schema, no linter and no pilot. Numbers such as
"~200 cells" and "45 → 15 minutes" are marked `open`: design intent, not
measurement.

## Layout

```text
skills/
  negative-test-first/
    SKILL.md
    README.md
    README.en.md
  evidence-first-docs/
    SKILL.md
    README.md
    README.en.md
    references/
      banned-words.md
      evidence-template.md
  invariant-first-code/
    SKILL.md
    README.md
    README.en.md
    references/
      invariant-template.md
      review-checklist.md
references/
  standards-map.md
  standards/
    SOURCES.md
    downloaded/
tools/
  claim_lint.py
  cell_lint.py
  status_diff.py
ci/
  claim-lint.yml
  cell-lint.yml
evals/
  evals.json
  iteration-1/
    RESULTS.md
  iteration-2/
    evals.json
    RESULTS.md
  linter/
    run_evals.py
    cases/
  cell-lint/
    run_evals.py
    cases/
  iteration-3/
    RESULTS.md
  iteration-4/
    RESULTS.md
spec/
  README.md
  conveyor/
    CONCEPT.md
    CONCEPT.en.md
    cell-registry.schema.json
    cells.seed.yaml
    guard-grammar.md
    guard-grammar.en.md
```

## Install

The skills are agent-neutral: each is a directory with a `SKILL.md`. Copy the
ones you need where your agent looks for skills.

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/negative-test-first ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

For another agent, put `SKILL.md` and its `references/` where that agent looks
for skills. The `README.md` next to a skill is for humans, not for context
loading.

## How to use

- Before a release: run `negative-test-first` over the claims and list the ones
  without a violating test.
- Before publishing a README or audit pack: run `evidence-first-docs` to
  remove unsupported absolutes and add scope.
- Before merging a security-sensitive change: run `invariant-first-code`
  through the checklist and verify the guard cannot be bypassed and the test
  fails when the guard is removed.
- After an incident: add a named lesson to a test, not only to a comment.

## Languages

- `SKILL.md` is English so the skill works in multilingual agents.
- `README.md` is Russian.
- `README.en.md` is English.
- The skills contain no language-specific annexes: examples and rules apply to
  any stack.

## Status

This is an early `0.1`: three skills, a crosswalk, evidence templates, skill
evals, two linter suites, and the `spec/` directory with the conveyor concept.
Results are in [`evals/iteration-1/RESULTS.md`](evals/iteration-1/RESULTS.md),
[`evals/iteration-2/RESULTS.md`](evals/iteration-2/RESULTS.md),
[`evals/iteration-3/RESULTS.md`](evals/iteration-3/RESULTS.md), and
[`evals/iteration-4/RESULTS.md`](evals/iteration-4/RESULTS.md). Planned:
executable checks for static analysis and trigger evals.

The executable part also includes `tools/cell_lint.py` (CL1–CL6: structure,
coverage, evidence, traceability, taxonomy, status-escalation gate) and the
`ci/cell-lint.yml` template. Its cases are in
[`evals/cell-lint/`](evals/cell-lint/) with results in
[`evals/iteration-4/RESULTS.md`](evals/iteration-4/RESULTS.md): 18/18, with a
runner negative control. These are synthetic fixtures, not proof that any
production registry is clean.

For now this is discipline and documentation, not a certificate or a substitute
for an audit.

## License

MIT — see [LICENSE](LICENSE). Third-party standards keep their own licenses;
see [`references/standards/SOURCES.md`](references/standards/SOURCES.md).
