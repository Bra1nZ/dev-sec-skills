# Iteration 1 Results

Date: 2026-11-02
Method: six prompts, each run with the skill loaded and without any skill
files (12 runs). Scores are assertion pass/fail by inspection, not automated
keyword matching.

## Summary

| Configuration | Assertions passed | Pass rate |
| --- | --- | --- |
| `with_skill` | 30 / 30 | 100% |
| `without_skill` | 28 / 30 | 93% |

The baseline is strong: current models already identify the main security
issues. The skill's measurable value is consistency, not rescuing a weak
answer. It forces statuses, scope, refusal classification, and explicit open
risks that the baseline often leaves implicit.

## Per-eval scores

| Eval | Skill | With skill | Baseline | Note |
| --- | --- | --- | --- | --- |
| `ntf-money-transfer` | negative-test-first | 5 / 5 | 4.5 / 5 | Baseline has strong concurrency and constraint coverage; skill adds explicit refusal-layer classification |
| `ntf-rls-review` | negative-test-first | 5 / 5 | 5 / 5 | Both cover cross-tenant UPDATE, roles, object scope, migration, and SQLSTATE classification |
| `docs-readme-claims` | evidence-first-docs | 5 / 5 | 4.5 / 5 | Baseline corrects the claims; skill adds mechanism/scope/status columns and named open claims |
| `docs-release-notes` | evidence-first-docs | 5 / 5 | 4 / 5 | Baseline is concise and mostly correct; skill adds residual risk and evidence freshness, but is much longer |
| `code-auth-review` | invariant-first-code | 5 / 5 | 5 / 5 | Both identify the batch/ORM bypass, body-controlled tenant, object-level gap, and missing RLS |
| `code-tenant-invariants` | invariant-first-code | 5 / 5 | 5 / 5 | Both cover tenant isolation, explicit admin grants, idempotency, fencing, and rotation |

## Qualitative findings

### What the skills improved

- `negative-test-first` produced an explicit claim -> negative-test index and
  a refusal-layer table. The baseline had the tests but less often said who
  refused and why that matters.
- `evidence-first-docs` produced a claim ledger with mechanism, evidence,
  scope, status, limitations, and `last verified`. The baseline produced a
  useful disposition table but omitted the status/scope fields.
- `evidence-first-docs` marked release-note claims as `tested`, `tested
  (stale)`, or `open`, and separated residual risk. The baseline had a "Not
  Verified" section but no evidence-freshness record.
- `invariant-first-code` produced an invariant map with enforcement points
  and failure modes. The baseline also did this well; the skill mainly
  standardized the shape and made the "verify the verifier" step explicit.

### What needs tuning

- **Verbosity.** `code-tenant-invariants/with_skill` is 92 KB for five
  requirements; `docs-release-notes/with_skill` is 9.6 KB for a short release
  note. Both are thorough, but the output should scale to the artifact. The
  skills now include a "scale the output" instruction.
- **Invented platform details.** The multi-tenant design chose PostgreSQL
  15/16 and specific lease/keyring timings although the prompt did not name a
  platform. It labeled them as a reference platform, but the skill should
  prefer an explicit assumption or a question. The code skill now says so.
- **Baseline strength.** On these prompts, a strong model without the skill
  already finds the main issues. Future evals should include near-miss
  prompts where the skill must prevent a confident but unsupported claim, not
  only prompts with obvious security holes.

## Decision

The skills are usable. The next iteration should test trigger behavior and
harder near-miss cases: a document with one subtle overclaim, a test suite
with a false-positive negative, and an authorization design with a
platform-provided guard that masks a missing application invariant.

Iteration 2 is in [`../iteration-2/RESULTS.md`](../iteration-2/RESULTS.md).
