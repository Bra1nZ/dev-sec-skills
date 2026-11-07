# Claim Ledger Schema and Linter

Machine-readable claim ledger plus the executable subset of the
evidence-first contract. The ledger turns the prose discipline of
`evidence-first-docs` and `negative-test-first` into data a tool can check.

## Files

- `claim-ledger.schema.json` — JSON Schema (draft-07) for the ledger.
- `run-record.schema.json` — JSON Schema (draft-07) for `evidence[].run_record`.
- `tool-output.schema.json` — JSON Schema (draft-07) for `evidence[].tool_output`.
- `../tools/claim_lint.py` — the linter (Python 3 stdlib; PyYAML for `.yaml` ledgers).

## Ledger format

A ledger is a JSON or YAML document with a `claims` array. Each claim:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | stable ID, `C-<n>` |
| `claim` | yes | falsifiable statement |
| `mechanism` | yes | what makes the claim true |
| `evidence` | yes | list of records: `kind`, plus `artifact`, `command`, `commit`, `date`, `tests`, `run_record`, `tool_output`, `note` |
| `scope` | yes | `platforms`, `actors_excluded`, `assumptions` |
| `status` | yes | `proven` / `model-checked` / `tested` / `static-refinement` / `reviewed` / `open` |
| `limitations` | open only | known limits, next to the claim |
| `last_verified` | recommended | last rerun date |

A ledger may also carry a top-level `retired` list of `{id, reason, date}`
tombstones (V2-05). A claim leaves the ledger only through a tombstone with a
non-empty reason: `tools/status_diff.py` errors when a base claim disappears
without one, and the tombstone is append-only, so dropping it later is an error
too. `claim_lint` L1 rejects a tombstone with no reason, a duplicate, and one
that names a claim still present in `claims`.

### Run record

A `kind=test` evidence item may carry a `run_record` (V2-01/V2-02): `runner`,
`command`, `commit`, `exit_code`, `started_at`, `finished_at`, `log`,
`log_sha256`, `artifact_sha256`, `tests_run`, `tests_passed`. It is optional —
the linter warns when it is missing — because the pilot ledgers predate it.
With a record, L2 verifies:

- the log exists under `--run-log-root` (default `--root`) and its SHA-256
  matches `log_sha256`;
- the artifact exists under `--root` and its SHA-256 matches `artifact_sha256`;
- `finished_at`'s local date equals the evidence date, and `started_at` is not
  after it;
- `exit_code` is 0 for a non-open claim, and agrees with the log's summary;
- `tests_run`/`tests_passed` agree with the cargo or pytest summary line;
- every cited test ID appears on a log line that carries a status. The runner
  must name each test: cargo does by default, pytest needs `-v` or `-rA`.

Independently of the run record, L2 also anchors the artifact: when the root is
inside a git work tree, the artifact must exist at the cited commit (the run
record's `commit` if the evidence item has none) and its bytes must equal the
working tree's. A commit that resolves but predates the artifact, or a file
edited after the commit, is an error — that is the unrelated-commit control.
A synthetic fixture without `.git` skips the check instead of failing it.

The record does not prove the run happened: without an external anchor (C-13)
a forger can rewrite the record and the log together. It removes silent
re-dating and unexecuted citations, not determined fraud.

### Tool output

A `model-checked` or `proven` claim needs an `evidence[].tool_output`
(V2-10): `tool`, `command`, `output`, `output_sha256`, `exit_code`,
`finished_at` are required, and `version`, `commit`, `started_at`, `verdict`,
`bound` are optional. An artifact says a model or proof script exists; this
record says a tool ran over it and what it answered. L1 checks the shape and
commit/command agreement; L2 verifies:

- `output` exists under `--tool-output-root` (default `--root`) and its SHA-256
  matches `output_sha256`;
- `finished_at`'s local date equals the evidence date, and `started_at` is not
  after it;
- `exit_code` is 0 for a non-open claim — a failed tool run supports no status
  above `open`.

L4 errors when a `model-checked` or `proven` claim has no `tool_output`, and
when a `model-checked` claim's record states no `bound`: a bounded run whose
bound is unrecorded overstates what was explored. The record does not check the
tool's semantics or the soundness of the encoding, and without an external
anchor a consistent forgery passes, exactly as with run records.

## Checks

| Check | What it enforces |
| --- | --- |
| L1 | schema: required fields, ID format, unique IDs, enums, `kind=test` needs `tests`, `status=open` needs `limitations`, `run_record` and `tool_output` shape and commit/command agreement, a non-empty `claims` array (an empty ledger cannot pass vacuously), `retired` tombstones with reasons and no live IDs |
| L2 | evidence health: artifact exists, commit resolvable, artifact matches its blob at the cited commit, dates within `--max-age-days` (default 90), run-record hashes and counts, tool-output hash and exit code, cited tests appeared in the log |
| L3 | traceability: every test ID in `kind=test` evidence exists in the suite (`report("F8a ...")`, `def test_*`, or Rust `#[test] fn`) |
| L4 | consistency: status matches the strongest evidence channel; stronger evidence than status is a warning; `model-checked` and `proven` need a `tool_output`, `model-checked` also needs a bound |
| L5 | prose: unqualified absolutes in docs. Engine order: Vale (`styles/RussianAbsolutes` package) if the `vale` binary is available, fallback to the built-in line scanner |

## Usage

```
python3 tools/claim_lint.py --root <project-root> \
    --suite-glob "setup/*.py" [--run-log-root <dir>] \
    [--tool-output-root <dir>] <project-root>/docs/claims.yaml
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
