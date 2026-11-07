# Static-analysis evidence (V2-36)

A static-analysis finding is a review-queue entry, not a verdict. This layer
turns one engine run into a record a linter can check: which engine and rule
set produced the finding, over which commit, with which raw output, which
normalized report, and what happened to every finding afterwards. The contract
is `schemas/static-analysis-run.schema.json`; the checks are L1/L2/L4 in
`tools/claim_lint.py`.

The first recorded run is `ci-craft-i18n-2026-11-07`: Semgrep over the second
pilot's GitHub configuration, five findings. The translation-row taxonomy owns
no supply-chain cell, so F-003 and F-004 (mutable action refs) are routed
across pilots to CELL-001 in `spec/pilots/dev-sec-skills/cells.yaml`, and
F-001, F-002 and F-005 stay `out-of-scope`. The `covered` route was re-checked
on 2026-11-08 by running D-PINNED-ACTIONS read-only over the craft-i18n
workflow directory: it exits 1 and names `ci.yml:17` and `sonarcloud.yml:20`.

The second recorded run is the self-pilot: the same rules over this
repository's own `.github/`. Three findings at the pre-fix commit are triaged
`new`, routed to CELL-001 in `spec/pilots/dev-sec-skills/cells.yaml`, fixed in
a separate commit, and the post-fix run returns zero findings. That is the
first real exercise of `new`; before it, only synthetic linter cases used the
disposition.

## Files

- `rules/ci-supply-chain-2026-11-07.yml` — three rules authored in this
  repository, not copied from a registry.
- `rules/python-audit-2026-11-07.yml` — one authored Python rule
  (`execute(f"...")` / `%`-formatted SQL) used by the two-engine measurement.
  It carries the same `failure_class` as Bandit B608, but neither maps to a
  cell: `rbac_pg/CELL-010` is `input-validation`, the engines' class is
  `invalid-or-injected-input`. Both findings keep `cell: null`; the two-engine
  report records `cell_mapped: 0`.
- `runs/ci-craft-i18n-2026-11-07.sarif` — raw Semgrep SARIF at
  `tool.driver.name = "Semgrep OSS"`.
- `runs/ci-craft-i18n-2026-11-07.report.json` — normalized report from
  `tools/sarif_evidence.py`.
- `runs/ci-dev-sec-skills-prefix-2026-11-07.{sarif,report.json}` — the
  self-pilot run at `d0c25c2`, three findings.
- `runs/ci-dev-sec-skills-postfix-2026-11-07.{sarif,report.json}` — the
  control run at `67d0aec`, zero findings.
- `anchor/allowed_signers` — the committed public key that pins the anchor
  signer. The private key is not in the repository.
- `anchor/ci-dev-sec-skills-{prefix,postfix}-2026-11-07.json{,.sig}` and
  `anchor/ci-craft-i18n-2026-11-07.json{,.sig}` — canonical subjects and their
  detached signatures, one pair per anchored run.

The claim that cites this run is C-09 in
`spec/pilots/craft-i18n/claims.yaml`. Its triage is embedded in the record, as
decided for this channel: one finding, one disposition, in the same bytes as
the output hashes. A second sidecar format and a second gate were the
alternatives; embedding keeps the finding-to-decision link inside the hashed
record.

## Why the rules are authored, not vendored

The first attempt used the Semgrep Registry `p/ci` rules. They produce four
findings on the same target, but the Semgrep Rules License v1.0 (`license:
Semgrep Rules License v1.0` in every rule's metadata) does not allow
distribution: "This license does not allow you to distribute the rules, or to
make them available to others as a service." Committing the rule file or a
SARIF document that embeds `tool.driver.rules` would redistribute them, so
neither is committed. The authored rule set covers the same failure classes the
pilot needed a sample for:

| Rule | What it matches | Finding in the pilot |
| --- | --- | --- |
| `dev-sec-skills.ci.mutable-action-ref` | a `uses:` reference at `@vN`, `@main` or `@master` | 2 |
| `dev-sec-skills.ci.secrets-inherit` | a reusable-workflow call with `secrets: inherit` | 1 |
| `dev-sec-skills.ci.dependabot-missing-cooldown` | a Dependabot update block with no `cooldown:` | 2 |

The rules are MIT, like this repository, and the table's counts are measured,
not estimated. The rules live under `languages: [generic]` and use
`pattern-regex` with `paths.include`; they are text rules, not data-flow
analysis, and that limit is stated in C-09.

## The recorded run

| Field | Value |
| --- | --- |
| Target | `/home/admini/projects/astraoffice/craft-i18n` |
| Commit | `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` |
| Engine | Semgrep OSS 1.184.0 |
| Rule set SHA-256 | `d05187dbf00f477bbaccf6e83c82f2ae5995e31936b44e5f462220ce9d54663d` |
| SARIF SHA-256 | `3e32c249edb0f8de52e581424d555a3fe29aed289019102580d5d24050166709` |
| Report SHA-256 | `6ed91da2891c42d106cf54978385ae46d60d78ca484e7182102b2757055b7779` |
| Started | `2026-11-07T22:54:14+03:00` |
| Finished | `2026-11-07T22:54:20+03:00` |
| Exit code | 0 |
| Status | `completed` |
| Findings | 5 |
| Unmapped | 0 |
| Fixture inputs | 0 |
| Duplicates | 0 |
| Report digest | `2c9ace2359dd4a796654ef9b899141cde01ac593f858edb2af6383111724ccea` |

The engine command, as recorded:

```bash
cd spec/static-analysis/rules && \
PATH=/tmp/opencode/semgrep-site/bin:$PATH \
PYTHONPATH=/tmp/opencode/semgrep-site \
SEMGREP_SEND_METRICS=off \
timeout 300 semgrep scan \
  --config ci-supply-chain-2026-11-07.yml \
  --sarif --output ../../static-analysis/runs/ci-craft-i18n-2026-11-07.sarif \
  --quiet --disable-version-check --metrics off \
  /home/admini/projects/astraoffice/craft-i18n
```

The normalized report:

```bash
python3 tools/sarif_evidence.py \
  --config spec/sarif/adapters.yaml --root . \
  --path-root /home/admini/projects/astraoffice/craft-i18n \
  --max-unmapped 0 --reject-fixtures \
  --json spec/static-analysis/runs/ci-craft-i18n-2026-11-07.report.json \
  spec/static-analysis/runs/ci-craft-i18n-2026-11-07.sarif
```

`--path-root` makes finding paths target-relative; `--root .` keeps the
adapter registries and the input path relative to this repository. Semgrep was
installed into a throwaway `/tmp/opencode/semgrep-site` prefix because
`/home` was nearly full and `python3 -m venv` is unavailable on this machine
(no `ensurepip`). That prefix is cleared on reboot; the committed SARIF, report
and rules are the evidence, and a replay needs `semgrep` 1.184.0 installed
again. `--config` is relative on purpose: an absolute path prefixes every rule
ID with the path, which breaks stable adapter mappings.

## The self-pilot run: three findings become `new`

The self-pilot analyzes this repository, not a read-only target. The pre-fix
commit still carried the mutable refs; the fix is `67d0aec`; the post-fix
commit is the fix.

| Field | Pre-fix | Post-fix |
| --- | --- | --- |
| Target | `/home/admini/projects/dev-sec-skills` | same |
| Commit | `d0c25c239522371a96dce47caa9bf056d068eb75` | `67d0aecb3c3ee929f5cf2debfed00f14772b0b3e` |
| Engine | Semgrep OSS 1.184.0 | same |
| Rule set SHA-256 | `d05187db…` | `d05187db…` |
| SARIF SHA-256 | `2b09702b…` | `b8073caf…` |
| Report SHA-256 | `f631739f…` | `6e6d746b…` |
| Findings | 3 | 0 |
| Unmapped / fixture | 0 / 0 | 0 / 0 |
| Status | `completed`, exit 0 | `completed`, exit 0 |

| Finding | Location | Disposition | Route |
| --- | --- | --- | --- |
| F-001 | `.github/workflows/fuzz-nightly.yml:27` | `new` | CELL-001 / D-PINNED-ACTIONS / MUT-001 |
| F-002 | `.github/workflows/fuzz-nightly.yml:29` | `new` | same |
| F-003 | `.github/workflows/fuzz-nightly.yml:70` | `new` | same |

`new` requires the named cell, detector and fixture to exist, and they do:
CELL-001 is `mutable-ci-action-ref`, the detector scans every non-local
`uses:` reference for a 40-hex commit, and MUT-001 turns a pinned ref back
into `@v7` and requires the detector to fail. The claim is C-01 in
`spec/pilots/dev-sec-skills/claims.yaml`; the pilot's own notes are in
`spec/pilots/dev-sec-skills/README.md`.

The post-fix run is the control, not a second opinion: the same rule file
(same SHA-256) over the same tree returns zero findings. A zero before the
fix would have shown the rule set was blind, not that the fix worked.

## Two engines, one report

`two-engine-2026-11-07.md` records the C-08 measurement: Bandit 1.9.4 and
Semgrep 1.184.0 over `rbac_pg/setup` at `d978609`, normalized together with
`--require-engines 2 --max-unmapped 0`. The three commands took 10.018 s in
total; the report has 249 findings, both engines present, 0 unmapped, 0
duplicates and 0 fixture inputs. The findings are not triaged, so the
measurement says nothing about coverage; C-08 stays `open`.

## Triage: five findings, five decisions

The pilot taxonomy is the translation-row grammar of `docs/catalog-format.md`.
All five findings are real configuration gaps, and none belongs to a cell of
`spec/pilots/craft-i18n/cells.yaml`. `out-of-scope` records that honestly:
the finding is neither dropped nor called a false positive.

| Finding | Location | Disposition | Reason (short) |
| --- | --- | --- | --- |
| F-001 | `.github/dependabot.yml:4` | `out-of-scope` | no Dependabot cooldown; no supply-chain cell in this pilot |
| F-002 | `.github/dependabot.yml:19` | `out-of-scope` | same boundary as F-001 |
| F-003 | `.github/workflows/ci.yml:17` | `out-of-scope` | `actions/checkout@v7` is a mutable tag; CI pinning is repository policy, not a catalog invariant |
| F-004 | `.github/workflows/sonarcloud.yml:20` | `out-of-scope` | the reusable workflow is called at `@main` |
| F-005 | `.github/workflows/sonarcloud.yml:21` | `out-of-scope` | `secrets: inherit` exposes every caller secret to the called workflow |

The target is read-only in this pilot, so no detector and no mutation fixture
were added; `new` would have required both. The seed registry has a
supply-chain cell (CELL-011) but it is outside the pilot's boundary, which is
why the reason says so instead of pointing at it.

## What the record proves, and what it does not

L2 proves that the rule file, the SARIF and the report hash to the cited
bytes; that the report hashes the same SARIF as an input; that the named
engine has a run in the report; that no finding is unmapped or authored; that
every finding has exactly one disposition; and that a routed entry resolves.
A URL for the SARIF or the report is rejected for a non-open claim: without
local bytes neither the hash nor the triage can be checked. The `covered` and
`new` paths are exercised by the linter evals, and the self-pilot above
exercises `new` for real; `covered` (a finding an existing detector already
caught) is still synthetic-only.

It does not prove that a finding is exploitable, that `out-of-scope` is a
harmless finding, or that the engine would catch a different defect. The rules
are authored here and are not the `p/ci` benchmark, so a different rule set
would produce a different review queue. The anchor below narrows a consistent
rewrite, but it does not remove the key-holder and `allowed_signers` gaps.

## Anchor: what it narrows and what it does not

Every static-analysis run carries an `anchor`: an ed25519 SSH signature over
the canonical bytes of the record. `tools/anchor_subject.py` defines those
bytes (engine and version, command, rule hashes, target commit, both output
hashes, exit code, timestamps, status, the `cells` registry and the whole
triage list);
`tools/anchor_run.py` signs and verifies; L2 recomputes the bytes and calls
`ssh-keygen -Y verify` against `spec/static-analysis/anchor/allowed_signers`.
The anchor is checked before the output paths, so a URL output cannot bypass
it.

The private key lives at `/tmp/opencode/dev-sec-skills-anchor/key`, outside
the repository, and is never committed. That is what makes an edit after
signing detectable: changing a disposition, a hash or a timestamp changes the
canonical bytes, and a forger without the key cannot produce a matching
signature. The `forge-anchored-record` red-team drill flips one triage
disposition and is blocked with `anchor subject does not describe this
record`.

The gap C-13 records is narrower, not closed. The key holder can re-sign any
edit, and anyone who can replace `allowed_signers` and re-sign can do the
same. There is no transparency log, timestamping or key revocation. The anchor
covers hashes, not the `output`/`report` paths or `rules.source`, and it covers
`static_analysis_runs` only: test run records, sanitizer, proof and review
records are not anchored.

Verification is offline. `ssh-keygen` must be on `PATH`; when it is missing a
non-open claim gets an error and an open claim gets info, so the failure is
visible rather than ignored. Losing the private key makes re-signing old
records impossible; those records stay valid, and new records would use a new
signer.

## Reproduce the checks

```bash
# the claim, including the static-analysis record and its triage
python3 tools/claim_lint.py \
    --root /home/admini/projects/astraoffice/craft-i18n \
    --suite-glob "crates/craft-i18n-tests/**/*.rs" \
    --run-log-root "$PWD" --tool-output-root "$PWD" \
    spec/pilots/craft-i18n/claims.yaml

# the linter cases for this channel
python3 evals/linter/run_evals.py

# the adapter cases (aliases and --path-root)
python3 evals/sarif/run_evals.py

# verify the committed anchors directly (offline; needs ssh-keygen)
python3 tools/anchor_run.py verify \
    --ledger spec/pilots/dev-sec-skills/claims.yaml --claim C-01 --run 0
python3 tools/anchor_run.py verify \
    --ledger spec/pilots/dev-sec-skills/claims.yaml --claim C-01 --run 1
python3 tools/anchor_run.py verify \
    --ledger spec/pilots/craft-i18n/claims.yaml --claim C-09 --run 0
```
