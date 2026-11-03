# Iteration 2 Results

Date: 2026-11-02
Method: three near-miss prompts, each run with the skill loaded and without any
skill files (6 runs). These prompts deliberately include a weak guard or stale
evidence that can sound acceptable in a confident review.

## Summary

| Configuration | Assertions passed | Pass rate |
| --- | --- | --- |
| `with_skill` | 15 / 15 | 100% |
| `without_skill` | 14 / 15 | 93% |

The baseline remains strong. It caught the central near-miss in every task.
The skill's advantage is a complete claim/test map and an explicit statement of
what remains unproven, not a rescue from a missed vulnerability.

## Per-eval scores

| Eval | Skill | With skill | Baseline | Note |
| --- | --- | --- | --- | --- |
| `docs-near-miss-release` | evidence-first-docs | 5 / 5 | 5 / 5 | Baseline qualified the claims well; with-skill refused to mark the release cleared and kept every claim `open` |
| `ntf-weak-negative` | negative-test-first | 5 / 5 | 4 / 5 | Baseline caught the deny mock and status-only oracle; it did not require mutation checks or an admin-without-grant case |
| `code-platform-masks` | invariant-first-code | 5 / 5 | 5 / 5 | Both found the owner/BYPASSRLS and `SECURITY DEFINER` bypasses; with-skill added production-role, pooler, restore, and mutation tests |

## Qualitative findings

- **The docs baseline is genuinely good.** It identified positional inserts,
  `SELECT *` decoders, volatile defaults, lock behavior, stale ASAN, and
  unexercised rollback. It still used `Cleared for canary deployment` and
  `Low to moderate` without an evidence basis. The skill output made the
  release conditional and recorded seven `open` claims instead.
- **The weak-negative baseline found the important defect.** It called the
  403-on-PATCH an existence oracle and the deny-only mock tautological. The
  skill output added a 12-row claim map, 21 named tests, and a seven-mutant
  kill matrix, which is a more reusable review artifact.
- **The platform-mask baseline found all three critical bypasses.** The skill
  output added invariant IDs, release-blocking test markers, connection-pool
  residue, `SECURITY DEFINER` hardening, restore checks, and explicit
  fail-closed conditions.

## Decision

No regression. The skills standardize the artifact and reduce omitted
qualifiers, but a strong model already finds the main issues when the prompt
names the suspicious facts.

The next eval round should remove explicit cues ("do not overclaim", "produce
a claim map", "list the tests") and test whether the skill description alone
makes the agent apply the discipline. It should also run on a weaker model;
that is where the consistency gain is likely to be largest.
