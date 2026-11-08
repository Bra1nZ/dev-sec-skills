# Handover: bring it up, run it, do not break it

This document is for the person taking the repository over. It does not replace
`README.en.md` (what this is and why) or `spec/README.md` (what lives under
`spec/`); it covers the environment, the gates, the change ritual and the known
holes.

## 1. What is handed over

- Three skills in `skills/` — `evidence-first-docs`, `invariant-first-code`,
  `negative-test-first`.
- Executable gates in `tools/` and `evals/`: the claim-ledger linter L1–L6, the
  cell linter CL1–CL6, the status-escalation gate, the verdict journal, the
  anchors, coverage reports, and the bootstrap path for a foreign repository.
- Knowledge in `spec/`: the concept (`spec/conveyor/CONCEPT.md` is the Russian
  source of truth), two pilots, the verdict journal, anchors, red-team drills,
  and the invariant and SARIF catalogues.
- None of it is a certificate. A green run means the registries, ledgers,
  journal and evals agree with each other.

## 2. Requirements and sibling checkouts

| What | Where | Commit | Why | Rights |
| --- | --- | --- | --- | --- |
| Python | 3.11+ | — | every tool | — |
| PyYAML | `pip install pyyaml` | — | reads registries and ledgers | — |
| OpenSSH `ssh-keygen` | system | — | signs and verifies anchors and the journal head | — |
| git | system | — | J3, L2, `status_diff` | — |
| Vale | optional | — | L5 prose; without it the linter falls back to `--no-vale` | — |
| First pilot | `../rbac_pg` | `d97860929b40a7a1f65e7b6a8cef66e72ef1cf4f` | `lint-pilot`, `claims-pilot`, `claims-static-rbac`, `coverage`, `mutations` | **read-only**, no remote configured |
| Second pilot | `../astraoffice/craft-i18n` | `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` | `lint-pilot2`, `claims-pilot2`, `mutations-i18n`, `coverage` | **read-only**, SSH remote |

The siblings must sit at exactly these relative paths: the Makefile resolves
them through `PILOT_ROOT` and `PILOT2_ROOT`. A missing directory fails the
target instead of skipping the gate — on purpose.

`../rbac_pg` carries a stale vendored copy of `claim_lint.py`. Do not fix it:
the pilot is read-only and the current linter lives in this repository.

## 3. First run

```bash
git clone <repo-url> dev-sec-skills
cd dev-sec-skills
git clone <rbac_pg-url> ../rbac_pg
git clone <craft-i18n-url> ../astraoffice/craft-i18n
python3 -m pip install --user pyyaml
make verify
```

Expected: `total: 0 error(s)` for every target, exit 0. The self-pilot reports
72 pre-existing warnings from the `RussianAbsolutes` L5 rule — not a
regression; watch the delta, not the absolute number.

A full `make verify` needs the siblings. Without them `make verify-ci` runs the
same gates minus the pilot checkouts, and that is what CI runs.

## 4. Gates

| Command | What it checks | Needs siblings | In CI |
| --- | --- | --- | --- |
| `make verify-ci` | evals, the self-pilot registry and ledger, the journal J1–J4, `unroutable`, invariants, `status-pilot2` | no | yes |
| `make verify` | the same plus both pilot registries, their ledgers and the coverage report | yes | no |
| `make journal` | J1–J4: the chain, ledger agreement, the prefix against `HEAD`, the canonical head and its signature | no | yes |
| `make journal-append` | appends changed verdicts and re-signs the head; needs the private key | no | no |
| `make red-team` | 20 attacks on the real artifacts: 18 blocked, 2 allowed (recorded holes) | yes | no |
| `make verify-all` | `verify` plus both mutation batches (PostgreSQL and cargo) | yes | no |

The journal is a separate layer: `spec/journal/README.md` covers its threat
model, the entry format and what the gate does **not** catch. Read it before
the first ledger edit.

## 5. Change ritual

1. Edit code or a ledger.
2. `make verify-ci` (or `make verify` with the siblings). A red gate is not
   bypassed by editing the gate.
3. If a claim's status or its evidence identity changed — `make journal-append`.
   The gate refuses to continue a broken chain, head or history.
4. Commit. If the journal changed, it and the head signature travel in the same
   commit as the ledger; otherwise J2/J4 go red.

A claim's status does not rise without new evidence — `tools/status_diff.py`
enforces that. A prose, `limitations` or `note` edit is not new evidence; it
changes only the ledger bytes the signed head covers, so `journal-append`
re-signs the head without adding an entry.

## 6. Keys

| Key | Private half | Public half | Signs |
| --- | --- | --- | --- |
| `dev-sec-skills-anchor-2026-11-07` | **lost** (was in `/tmp`) | `spec/anchor/allowed_signers` | 13 older anchors |
| `dev-sec-skills-anchor-2026-11-08` | `~/.config/dev-sec-skills/anchor/key` (600) | same directory | 4 anchors, the journal head |

- Private keys never enter the repository; `allowed_signers` is public and
  committed.
- Rotation is an edit to `spec/anchor/allowed_signers`; the procedure is in
  `spec/anchor/README.md`.
- Losing the 2026-11-08 key means the journal head cannot be re-signed: add a
  new identity and record the loss in the claim's limitations instead of
  pretending a signature proves anything about the date.
- `make verify*` needs no private key: CI verifies signatures but does not
  create them. CI holds no secrets.

## 7. What is known and what is open

The open holes are recorded in the claims and in the concept; here is the map:

- **C-08 / CELL-002** — a real gap: `craft-i18n` lets invisible Unicode Cf
  characters through. The claim is open; the evidence is a probe under
  `spec/pilots/craft-i18n/probes/`.
- **C-13** — the journal closes silent rewriting of the past within one key
  holder. There is no transparency log, timestamping or revocation; the key
  holder, or anyone who can replace `allowed_signers` and rewrite git history,
  bypasses everything. The red-team drill `rewrite-journal-and-resign` is
  recorded as `allowed`.
- **C-07…C-12** — hypotheses: no product runs, no statistics.
- **V2-33** — the product-trial boundary is filled when the first product
  sprint opens.
- **CI is partial**: `verify-pilot`, `verify-pilot2`, `coverage` and
  `red-team` need the siblings and stay local.
- **The external `rbac_pg` ledger** (`../rbac_pg/docs/claims.yaml`) is
  deliberately outside the journal: a `../` path would tie the journal to one
  layout. Its verdicts are not covered by the hash chain.
- **proof and review records are not anchored**: an edit inside `tool_output`
  or a review note changes no evidence identity and needs no journal entry.
- **L5 noise**: 72 pre-existing warnings in the self-pilot; a new one is easy
  to lose. There is no threshold because none has been measured.
- **Vale is not installed in CI**: L5 degrades to `--no-vale` there. Prose is
  checked locally only.

## 8. First week

1. Run `make verify` and confirm exit 0 and the warning count from this
   document.
2. Read `spec/journal/README.md` and
   `spec/pilots/dev-sec-skills/claims.yaml` (C-42 is a complete claim with an
   anchor).
3. Run `make red-team` and look at the two `allowed` drills: that is the
   boundary of the threat model, not a bug.
4. Check the first `verify.yml` run in Actions. Green means the gate works in
   CI; red means fix it before the first edit.
5. Pick the next increment from the open holes. The cheapest in risk is C-08;
   the most expensive is C-13 (external footing).

## 9. Boundaries of this handover

- Keys are not part of the repository; they live in `~/.config`.
- The two pilot checkouts are foreign repositories; do not touch their
  uncommitted changes.
- `spec/pilots/rbac_pg/analysis-claims.yaml` holds 249 `not-a-bug` records:
  that is a triage, not proof of safety.
- Anything not recorded in a claim with a status and evidence is an intention,
  not a property. Read it that way.
