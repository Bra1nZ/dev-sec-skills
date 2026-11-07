# Self-pilot — dev-sec-skills against its own CI

The first two pilots are read-only: their findings can only be triaged
`out-of-scope` or `not-a-bug`, because fixing the target is outside the
pilot's boundary. That left the `covered` and `new` dispositions exercised
only by synthetic linter cases. This pilot removes the boundary by pointing
the channel at dev-sec-skills itself.

## What was measured

| Step | Commit | Engine | Findings | Triage |
| --- | --- | --- | --- | --- |
| Pre-fix run | `d0c25c2` | Semgrep OSS 1.184.0, `ci-supply-chain-2026-11-07` | 3 | 3 × `new` → CELL-001 |
| Fix | `67d0aec` | — | — | three `uses:` refs pinned to commit SHAs |
| Post-fix run | `67d0aec` | same engine and rule set | 0 | — |

The three findings are the same failure class: a `uses:` reference at `@v7`
instead of a commit SHA in `.github/workflows/fuzz-nightly.yml` (lines 27, 29
and 70 at the pre-fix commit). No detector existed at `d0c25c2`, so `new` is
the honest disposition: the finding opened the cell, the detector and the
fixture, and the fix landed in a separate commit.

The post-fix run is the control. It is the same engine, the same rule file
(same SHA-256) and the same repository, and it returns zero findings. A run
that returned zero before the fix would prove the rule set, not the fix.

## Files

- `cells.yaml` — CELL-001 (`mutable-ci-action-ref`, `security`), detector
  D-PINNED-ACTIONS.
- `claims.yaml` — C-01, the pre-fix and post-fix runs, the triage, and the
  detector run record.
- `detectors/test_ci_supply_chain.py` — the detector. Dependency-free: its
  `def test_*` functions are the test IDs `cell_lint` resolves, and
  `python3 <file>` runs them with a pytest-shaped log.
- `mutations/mutations.yaml` + `mutations/run_mutations.py` — MUT-001.
- `probes/pinned-ci/` — the clean control tree MUT-001 copies and mutates.

The raw evidence is in `spec/static-analysis/runs/`:
`ci-dev-sec-skills-prefix-2026-11-07.*` and
`ci-dev-sec-skills-postfix-2026-11-07.*`.

## What the detector does and does not cover

It scans every non-local `uses:` reference in `.github/workflows` and requires
`@<40 hex>`. A local action (`./path`) is allowed because its bytes are the
repository commit; a `docker://` reference is skipped because image digests
are a different failure class. The detector is a text scan: it fixes the
reference, not the intent of the action, and it says nothing about the runner
that fetches it.

MUT-001 is the falsifiability control. It copies the probe, turns one pinned
action back into `@v7`, and requires exactly
`test_workflow_actions_are_pinned` to fail. The repository itself is never
modified.

## Reproduce

```bash
make lint-self claims-self detectors-self
make mutations-self
```

`make verify` includes `verify-self`, so the detector runs on every gate. The
mutation fixture is hermetic but is kept out of `verify` and included in
`verify-all`, matching the other mutation batches.
