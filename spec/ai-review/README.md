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

## Open questions

- pr-agent × hub integration: model naming via LiteLLM config, behavior
  at the D2 boundary on large diffs, latency per review.
- Whether the prepush gate should open an ephemeral draft PR for
  PR-centric engines, or engines must accept a plain diff.
- Baseline linters (shellcheck, pyflakes, actionlint) are still not in
  `verify-ci`; until they are, "beyond static gates" claims are weak.
