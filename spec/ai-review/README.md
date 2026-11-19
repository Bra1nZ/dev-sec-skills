# AI diff review — decisions and measurements

The working record for the "own CodeRabbit" line of work: an AI reviewer
for every change, driven by the project's own model hub. This file records
decisions with their evidence so they survive context loss. It is not a
channel record: findings from the reviewer are triage input, not evidence,
and are not journaled (see `tools/ai_review.py` docstring for the current
honest limits).

## Hard constraints (non-negotiable, user-mandated)

1. The hub API key (`~/.config/codex-security/astra-api-key`) is never
   printed, committed, or placed in GitHub Secrets or any third-party
   secret store. The review therefore runs **locally** (pre-push gate,
   `tools/prepush.sh`), not as a cloud service.
2. The reviewer must target the project's own model hub
   (`hub.ai.astra-team.ru`, OpenAI-compatible chat/completions).
3. No pushing without explicit consent; the repo ritual is
   `make verify-ci TRANSPARENCY_GATE=1` → commit.

## D1 — build a replacement, not adopt a SaaS (2026-11-18)

CodeRabbit-class SaaS is out: it requires either the key in GitHub
Secrets or sending code to a third-party cloud, both forbidden. The MVP
(`tools/ai_review.py`, canary eval in `evals/ai-review/`) was built and
measured: planted-vulnerability canary caught 3/3 in ~15s; clean control
silent; on the reviewer's own 37k-char diff it found real bugs (an
undefined-name error in the eval timeout handler, dead code in the
workflow's canary-failure handler) — though those specific catches are
within reach of shellcheck/pyflakes, which is why the measurement plan
below compares against that baseline too.

## D2 — measured model constraint (2026-11-18, hub GLM-5.3)

The hub's GLM-5.3 is a reasoning model whose reasoning phase cannot be
turned off (`thinking: {"type": "disabled"}` accepted, not honored) and
whose reasoning length scales with payload size AND material density:
a ~10k-char payload answers in ~100s; 14k+ hits finish_reason=length with
empty content; 32k timed out at 300s. Whole-diff review is unreviewable
at any token budget. The MVP therefore reviews in chunks (full payload
under 9.5k chars) with adaptive truncation, loudly marked. Any engine we
run on this hub inherits this constraint — engine choice must respect it
or mitigate it by design (e.g. pr-agent's PR compression).

## D3 — pr-agent (MIT) is the adopt-candidate engine (2026-11-19)

Survey of open-source/closed alternatives against the constraints:

| Candidate | Verdict | Reason |
| --- | --- | --- |
| pr-agent (The-PR-Agent, MIT, 16.4k stars) | **adopt-candidate** | CLI/self-host; LiteLLM under the hood → our hub without key exposure; PR-compression strategy addresses D2 by design; /review /improve /ask gives the interactivity the MVP lacks; prompts configurable via toml without forking |
| pullfrog (MIT) | rejected | BYOK bot for GitHub Actions; the key inevitably lands in Actions secrets or the vendor's encrypted store — forbidden by the hard constraint (it wraps Claude Code/Codex/OpenCode; philosophically closest, architecturally incompatible) |
| greptile (closed SaaS) | not a candidate | no self-host below Enterprise; own cloud index. Its OSS free tier may serve as an independent external *measurement baseline* on this public repo, not as the working tool |
| cubic (closed SaaS) | not a candidate | own models, no custom endpoint; top of Code Review Bench but architecturally out of reach |

Decision: dig inside pr-agent (integrate it into the prepush gate against
the hub) instead of building the missing capabilities from scratch. The
MVP client remains in the repository as (a) the canary oracle and trust
preflight — no engine's findings are trusted if the planted diff is not
seen, (b) the fallback reviewer, (c) the reference for honest limits.

Known pr-agent caveats to resolve during integration: it is PR-centric
(`--pr_url`) while this repo pushes to main through the prepush gate
(need ephemeral draft PR or local-diff mode); it is community-maintained
after donation by Qodo (slower cadence, e.g. /help_docs disabled over a
credential-exposure bug in 2026).

### Integration measurement (2026-11-19, hub GLM-5.3 via LiteLLM)

pr-agent's plain-diff CLI mode (`--diff-file`) needs no PR at all — the
PR-centric caveat above is resolved. Working configuration:
`CONFIG__MODEL=openai/GLM-5.3`, `OPENAI__API_BASE=<hub>`,
`CONFIG__CUSTOM_MODEL_MAX_TOKENS=8000`, `CONFIG__AI_TIMEOUT=300`
(the default 120s times out before this reasoning model finishes),
`CONFIG__FALLBACK_MODELS=""` (the shipped default names models the hub
does not serve), and — the decisive find —
`PR_REVIEWER__ENABLE_LARGE_PR_CHUNKING=true`: pr-agent already contains
a complete chunked-review flow (split via `get_pr_multi_diffs`, batched
calls, finding merge, coverage accounting) that is simply disabled by
default for /review. Option C ("teach the engine multi-pass") turned out
to be a config discovery, not a development project.

Measured on the MVP's own 37k-char / 12.8k-token diff (13 files):

| Configuration | Result |
| --- | --- |
| default budget (32k) | full diff sent → the D2 reasoning wall: 2×120s timeouts, total failure; also: the CLI exits 0 on failure, the gate must check content |
| budget 4000, single-pass | 92s, compression kept 1 of 13 files; planted canary found, real code invisible; coverage honestly reported |
| budget 8000, single-pass | 89s, ~3 files reviewed, 3 real catches (broken exit-code contract, unescaped markdown in `render_markdown`, eval timeout race 300s < 363s worst case) |
| budget 8000 + chunking, ≤5 calls | **262s, all 13 files in 3 merged chunks**, honest "Chunked review" notice; canary 3/3; 3 real catches incl. a path-traversal vector in the MVP's `numbered_content` (diff-parsed paths read and sent to the hub) — found by neither the MVP's self-review nor single-pass runs |

Cross-engine comparison on identical inputs shows near-zero overlap of
findings: the MVP's chunked self-review caught an undefined-name bug and
dead workflow code; pr-agent's chunks caught the exit-code contract, the
markdown-injection vector, the eval timeout race, and the diff-path
traversal. One cross-chunk false positive ("Missing Fixtures" — the
fixtures were in a different chunk) is the known context-loss cost of
chunking, honestly visible in the output.

## D4 — the measurement plan is engine-independent (2026-11-19)

Any candidate engine (MVP or pr-agent) passes the same gates before its
findings are trusted:

1. Canary preflight: the planted diff (command injection, hardcoded
   credential, path traversal) must be seen; `--canary-only` mode of
   `evals/ai-review/run_evals.py`.
2. Retro-eval on known real bugs: rerun the reviewer on diffs that
   introduced defects which passed all static gates and human review
   (the craft-i18n C-08 invisible-character gap class; the project's own
   past slips). Measures recall on genuine defects without needing a
   CodeRabbit baseline.
3. Independent evaluator: an agent not privy to this work runs the gate
   on a canary-seeded branch and gives APPROVE/REQUEST CHANGES.
4. On live changes: noise rate (share of findings triaged to "not a bug")
   and recall of anything the author later found themselves.

Success criterion for building further (original D-decision, 2026-11-18):
if over a measurement period the reviewer catches nothing that the static
gates plus shellcheck/pyflakes/actionlint would not catch, stop building
and reconsider adoption; if it does, the missing capabilities
(dialogue, dedup, second engine) are built or adopted with pr-agent.

## Independent evaluator experiment (2026-11-19)

Question: can a reviewer with no context beyond the repository decide a
canary-seeded change correctly using our gate — the "comparable to
CodeRabbit" claim, tested end to end.

Setup: a worktree at `origin/main` plus one local seed commit adding
`tools/examples/stand_query.py` — byte-identical to the repo's canary
fixture (hardcoded `sk-live` token, `os.system` injection, path
traversal). Two independent agents, each with a neutral brief ("decide
whether the pending change is safe to push"), no hints.

Results:

| Run | Verdict | Gate behavior | Engine evidence |
| --- | --- | --- | --- |
| evaluator 1 | REQUEST CHANGES (high conf., ~3 min gate) | gate exited 0 despite high findings — flagged by the evaluator as the critical weakness | both engines independently reported all 3 planted mechanisms with exact file:line |
| evaluator 2 (after policy change) | REQUEST CHANGES (high conf., ~4 min gate) | gate exited 1, matching its documented blocking policy | same: MVP 2 high + 1 medium; pr-agent "Security concerns" |

Policy change (the experiment's direct outcome): the AI diff review in
`tools/prepush.sh` is now blocking at HIGH severity — a high finding
from either engine fails the gate (exit 1); medium/low stay advisory.
pr-agent has no numeric severities; its "Security concerns" section is
its highest-urgency bucket and is mapped to high. `--skip-ai-review`
remains the explicit human override. Measured basis: 0 false positives
on planted content across the 8-case retro corpus, 1 medium false
positive in the ensemble dogfood, no high-severity false positive
observed on any run.

Two defects the experiment itself caught, both fixed with negative
tests extracted from the script under test:

- Inversion (found by the first live blocking run, not by the unit
  test): the predicate's exit code and the call-site condition
  disagreed, so the gate stayed silent on high findings and would have
  blocked a clean diff. Lesson recorded: a policy test must go through
  the actual call site, not a retyped snippet.
- Fail-open edge (found by evaluator 2): a structurally malformed JSON
  report (`findings: null`, non-dict items) raised outside the guarded
  section and exited with the "clean" code. The parser now fails closed
  on every schema deviation — the report is gate-generated, so any
  deviation means corruption or tampering.

Honest caveat: both evaluators recognized the seeded file as identical
to the repo's public canary fixture — a legitimate move for a reviewer
with repository access, but an information edge a stranger would not
have. The engines themselves detected the issues from the diff alone;
the fixture recognition changed the framing, not the detection.

## Open questions

- pr-agent × hub integration: model naming via LiteLLM config, behavior
  at the D2 boundary on large diffs, latency per review.
- Whether the prepush gate should open an ephemeral draft PR for
  PR-centric engines, or engines must accept a plain diff.
- Baseline linters (shellcheck, pyflakes, actionlint) are still not in
  `verify-ci`; until they are, "beyond static gates" claims are weak.
