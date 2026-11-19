# Retro-eval corpus: known real bugs, both engines blind

A regression benchmark for AI diff-review engines. Every case is a
well-formed unified diff containing a bug that was real — committed,
shipped, or probe-proven somewhere in this project's history — not
synthetic filler. Engines are run blind (no hints about what is
planted) and judged against the ground truth below.

Method: each case's diff is fed to both engines exactly as the prepush
gate feeds them — the MVP reviewer (`tools/ai_review.py --diff ...`)
and pr-agent (`pr-agent --diff-file ... review`, chunked config, see
`spec/ai-review/README.md`). A case counts as caught only if a finding
addresses the planted defect's mechanism; nitpicks and extraction
artifacts are scored separately and do not count either way.

Corpus built 2026-11-19. Raw run outputs are ephemeral; the durable
record is the results table in this file.

## Cases

| # | Case | Planted defect (ground truth) | Origin |
| --- | --- | --- | --- |
| 01 | `01-makefile-recipe-glue.diff` | Two make recipes merged onto one tab-indented line: the second `$(PYTHON)` invocation becomes extra argv of the first, so the claim-format evals silently never run. | Real slip made and caught before commit during MVP build |
| 02 | `02-malformed-hunk-header.diff` | Hunk header declares `+1,9` but the body has 8 added lines; `git apply` rejects the patch. | Real defect committed in the MVP's fixtures (`c3a9423`), fixed in `b581c38` |
| 03 | `03-unicode-cf-filter-gap.diff` | `parse_row` rejects `c.is_control() \|\| c == '\u{feff}'` — Cc and U+FEFF only — so Unicode Cf formatting characters (U+200B, U+202E bidi override, U+2066) pass validation and change UI rendering. | Probe-proven open claim C-08 (`spec/pilots/craft-i18n/claims.yaml`); missed by a 19-minute LLM repo scan |
| 04 | `04-workflow-dead-paths.diff` | Three stacked defects: `bash -e` aborts before the `if [ $? -ne 0 ]` handler runs; the `!= 'skipped'` outcome guard drops the canary-failure comment; `workflow_dispatch` runs have an empty PR number and the posting call fails. | Real defect in the pre-ensemble `.github/workflows/ai-review.yml` |
| 05 | `05-path-traversal.diff` | `numbered_content` joins `repo_root` with a path parsed from the untrusted diff without containment: crafted `b/../..` paths (or committed symlinks) read files outside the checkout and send them to the hub. | Real defect found by pr-agent in the MVP's own diff, fixed with negative tests in `48b10e4` |
| 06 | `06-eval-timeout-race.diff` | The eval's `subprocess.run(timeout=300)` is shorter than the reviewer's worst case (~603s = 2 attempts × 300s + retry sleep), and `TimeoutExpired` is unhandled: a slow-but-successful run kills the whole harness instead of recording one FAIL. | Real defect in the MVP's eval, found by pr-agent, fixed in `48b10e4` |
| 07 | `07-markdown-injection.diff` | `render_markdown` interpolates model-derived `title`/`detail` into the report unescaped: prompt injection through a diff plants arbitrary markdown/HTML in the posted review; pipes/newlines break the table. | Real defect found by pr-agent, fixed with negative tests in `48b10e4` |
| 08 | `08-clean-control.diff` | Nothing planted. A correct, self-contained target file; the expected outcome is silence. | The repo's standing clean control (`evals/ai-review/fixtures/`) |

## Measured results (2026-11-19, hub GLM-5.3)

Both engines blind on all 8 cases. Scores against planted defects only;
findings about the corpus artifacts themselves (early partial-extract
versions had undefined constants) were true positives on the artifact
and are excluded here — the artifacts were fixed and the affected cases
re-run as v2.

| # | Case | MVP | pr-agent |
| --- | --- | --- | --- |
| 01 | recipe glue | caught (10s) | caught (24s) |
| 02 | hunk header | caught (63s) | caught (136s) |
| 03 | Cf-char gap | caught, low (266s) | **missed** (72s) |
| 04 | workflow dead paths | **failed** — hub wall, rc=4 (356s) | caught, all 3 mechanisms (127s) |
| 05 | path traversal | caught, high (107s) | caught (85s) |
| 06 | timeout race | caught, medium (62s) | caught (374s) |
| 07 | md injection | caught, medium (45s) | caught (38s) |
| 08 | clean control | silent (11s) | silent (18s) |

**Scores: MVP 6/7, pr-agent 6/7, union 7/7; control silent for both;
zero false positives on planted content.**

## What this corpus establishes

1. **Ensemble justification, measured.** Neither engine catches
   everything; their misses are class-shaped, not random: pr-agent does
   not know `char::is_control` semantics (Cc vs Cf) and missed the
   Unicode class; the MVP died on dense workflow YAML (see below).
   The union covers all 7.
2. **The reasoning wall is density-driven, not size-driven.** On case
   04 (3391-char diff) the MVP's adaptive retry fired and halved the
   chunk to ~1700 chars — still `finish_reason=length` with empty
   content. Sub-2k dense YAML can die while the 1555-char case 05
   passes. Char budgets alone cannot predict the wall.
3. **Independent confirmation of the step-2 fixes.** Cases 05–07 are
   the MVP's own defects found by the second engine; as standalone
   cases both engines now catch all of them.
4. **Noise baseline.** On the clean control both engines are silent;
   across all runs no engine produced a false positive on planted
   content. Known FP from the ensemble's first dogfood run (MVP claimed
   `--diff-file` is not a valid flag while pr-agent reviewed that very
   diff) is recorded in `spec/ai-review/README.md`.

## Re-running

The corpus is plain diffs; any engine can be scored against the table
above. For the MVP:

    python3 tools/ai_review.py --diff evals/ai-review/retro/cases/01-makefile-recipe-glue.diff \
      --repo-root . --out-json /tmp/retro.json --out-md /tmp/retro.md

For pr-agent, use the measured configuration from
`spec/ai-review/README.md` (chunking on, budget 8000, timeout 300).
A changed score on any case is a regression worth investigating before
trusting either engine's verdicts.
