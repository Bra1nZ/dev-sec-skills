# Claim Ledger Schema and Linter

Machine-readable claim ledger plus the executable subset of the
evidence-first contract. The ledger turns the prose discipline of
`evidence-first-docs` and `negative-test-first` into data a tool can check.

## Files

- `claim-ledger.schema.json` — JSON Schema (draft-07) for the ledger.
- `../tools/claim_lint.py` — the linter (Python 3 stdlib; PyYAML for `.yaml` ledgers).

## Ledger format

A ledger is a JSON or YAML document with a `claims` array. Each claim:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | stable ID, `C-<n>` |
| `claim` | yes | falsifiable statement |
| `mechanism` | yes | what makes the claim true |
| `evidence` | yes | list of records: `kind`, plus `artifact`, `command`, `commit`, `date`, `tests`, `note` |
| `scope` | yes | `platforms`, `actors_excluded`, `assumptions` |
| `status` | yes | `proven` / `model-checked` / `tested` / `static-refinement` / `reviewed` / `open` |
| `limitations` | open only | known limits, next to the claim |
| `last_verified` | recommended | last rerun date |

## Checks

| Check | What it enforces |
| --- | --- |
| L1 | schema: required fields, ID format, unique IDs, enums, `kind=test` needs `tests`, `status=open` needs `limitations` |
| L2 | evidence health: artifact exists, commit resolvable, dates within `--max-age-days` (default 90) |
| L3 | traceability: every test ID in `kind=test` evidence exists in the suite (`report("F8a ...")` or `def test_*`) |
| L4 | consistency: status matches the strongest evidence channel; stronger evidence than status is a warning |
| L5 | prose: unqualified absolutes in docs. Engine order: Vale (`styles/RussianAbsolutes` package) if the `vale` binary is available, fallback to the built-in line scanner |

## Usage

```
python3 tools/claim_lint.py --root <project-root> \
    --suite-glob "setup/*.py" <project-root>/docs/claims.yaml
```

Exit codes: 0 clean, 1 errors, 2 tool error. L5 warnings do not fail the run.

## Pilot results (rbac_pg, 2026-11-05)

Pilot ledger: `rbac_pg/docs/claims.yaml` — 7 claims derived from ROLES.md and
`docs/fstek-compliance.md`, test IDs cross-checked against
`setup/test_fstek.py` (57 report-based checks, IDs F2..F15b, M0..M6).

- L1–L4: clean on 7/7 claims; evidence anchored to real commits
  (`2e120b6`, 2026-10-30).
- L3/L4: caught a planted fixture (nonexistent test ID `F16` declared as
  `tested`) — 1/1 fabricated traceability rows detected.
- L5: 14 warnings on Russian docs, ~13 of them false positives: the word list
  fires on third-party references ("сертифицированная сборка", "гарантирует
  платформа" about other systems). Known precision gap: L5 needs a
  self-claim context rule before it can gate a merge.
- Lesson recorded: the first linter run itself contained a false-positive bug
  (glob matched filenames, not root-relative paths) — the tooling needs its
  own evals. "Verify the verifier" applies to the verifier.

This is a pilot, not a certification. The checks prove the ledger is
internally consistent and traceable; they do not prove the claims themselves.
