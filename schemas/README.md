# Claim Ledger Schema and Linter

Machine-readable claim ledger plus the executable subset of the
evidence-first contract. The ledger turns the prose discipline of
`evidence-first-docs` and `negative-test-first` into data a tool can check.

## Files

- `claim-ledger.schema.json` — JSON Schema (draft-07) for the ledger.
- `run-record.schema.json` — JSON Schema (draft-07) for `evidence[].run_record`.
- `tool-output.schema.json` — JSON Schema (draft-07) for `evidence[].tool_output`,
  written by `../tools/bounded_check.py` (V2-28).
- `sanitizer-run.schema.json` — JSON Schema (draft-07) for
  `evidence[].sanitizer_runs` (V2-35): one dynamic sanitizer run with its
  instrumentation flags, captured output and outcome.
- `fuzz-run.schema.json` — JSON Schema (draft-07) for a fuzz run record (V2-17),
  written by `../tools/fuzz_run.py`.
- `fuzz-triage.schema.json` — JSON Schema (draft-07) for the triage of one fuzz
  run record (V2-18), checked by `../tools/fuzz_triage.py`.
- `invariant-catalog.schema.json` — JSON Schema (draft-07) for the general-code
  invariant catalogue (V2-21), checked by `../tools/invariant_catalog.py`.
- `sarif-evidence.schema.json` — JSON Schema (draft-07) for the normalized SARIF
  evidence report (V2-23), written by `../tools/sarif_evidence.py`.
- `proof-manifest.schema.json` — JSON Schema (draft-07) for the proof manifest
  (V2-29), read by `../tools/proof_plan.py`; it declares which code, model,
  encoding and tooling a proof depends on.
- `../tools/claim_lint.py` — the linter (Python 3 stdlib; PyYAML for `.yaml` ledgers).

## Ledger format

A ledger is a JSON or YAML document with a `claims` array. Each claim:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | stable ID, `C-<n>` |
| `claim` | yes | falsifiable statement |
| `mechanism` | yes | what makes the claim true |
| `evidence` | yes | list of records: `kind`, plus `artifact`, `command`, `commit`, `date`, `tests`, `shared_tests`, `run_record`, `tool_output`, `sanitizer_runs`, `note` |
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

### Proof manifest

A manifest (V2-29) is `{version: 1, proofs: [...]}`. Each entry declares `id`,
`claim`, `artifact`, `tool_output`, `depends_on`, `assumptions`, and optionally
`model`, `encoding`, `tooling`, `proven_commit`, `proven_at`, `owner`, `note`.
`depends_on` and `assumptions` are required and may not be empty: a proof whose
boundaries are unwritten is an overclaim, and a proof with no declared
dependency can never be invalidated by a diff. The loader rejects those, a
duplicate ID, and an `artifact` that does not exist with exit 2.
`../tools/proof_plan.py` compares the manifest against a git range and prints
which proofs must be re-run; `../spec/proofs/manifest.yaml` is empty because no
claim in this repository is `proven`. The schema does not encode freshness:
that is a comparison of the record's `finished_at` against commit times, and it
is described in `../spec/proofs/README.md`.

### Shared tests (V2-34)

A test may legitimately support more than one claim, so the schema does not
force test IDs to be unique. Instead, a `kind=test` evidence item lists the
shared IDs in `shared_tests: [{id, reason}]`, where `id` is one of its own
`tests` and `reason` is a non-empty explanation of why the test is evidence for
*this* claim. L1 checks that shape. L6 then enforces two rules:

1. a test cited by two or more claims must be declared in `shared_tests` by
   every citing claim;
2. a non-open claim must cite at least one test that no other claim cites.

The second rule is what makes the declaration insufficient by itself: moving a
claim onto a neighbour's tests does not inherit the neighbour's evidence.
`open` is exempt from rule 2 because it claims no evidence status. Neither rule
compares the test's assertions with the claim's wording, so one own-but-
irrelevant citation still passes; that remains a human review question.

### Tool output

A `model-checked` or `proven` claim needs an `evidence[].tool_output`
(V2-10): `tool`, `command`, `output`, `output_sha256`, `exit_code`,
`finished_at` and `status` are required, and `version`, `commit`, `started_at`,
`verdict`, `bound`, `timed_out`, `bound_seconds`, `elapsed_seconds` are
optional. An artifact says a model or proof script exists; this record says a
tool ran over it and what it answered. L1 checks the shape and commit/command
agreement; L2 verifies:

- `output` exists under `--tool-output-root` (default `--root`) and its SHA-256
  matches `output_sha256`;
- `finished_at`'s local date equals the evidence date, and `started_at` is not
  after it;
- `exit_code` is 0 for a non-open claim — a failed tool run supports no status
  above `open`;
- `status` is `completed` for a non-open claim, and `timed_out` is false
  (V2-28). `unverified`, `failed` and `error` say the run did not decide
  anything, so they cannot support a status above `open` even when an artifact
  or a log exists.

`status` has four values: `completed` (the process exited before the bound),
`unverified` (the wall-clock bound elapsed and the process group was killed, or
the tool said it could not decide), `failed` (non-zero exit before the bound)
and `error` (the supervisor could not start or watch the process). L1 rejects
`timed_out: true` with any status other than `unverified`, because one of the
two fields would be false. `tools/bounded_check.py` writes this record: it
starts the command in its own session, kills the whole group at `--timeout`,
and writes the combined log without adding supervisor lines, so
`output_sha256` covers the tool's bytes only. Exit codes are 0 completed,
1 failed, 2 usage or supervision error, 3 unverified.

L4 errors when a `model-checked` or `proven` claim has no `tool_output`, and
when a `model-checked` claim's record states no `bound`: a bounded run whose
bound is unrecorded overstates what was explored. The record does not check the
tool's semantics or the soundness of the encoding, and without an external
anchor a consistent forgery passes, exactly as with run records. A `completed`
run is not a proof: `verdict` stays the tool's own line in the log, and the
supervisor does not paraphrase it.

### Sanitizer run (V2-35)

A sanitizer run is dynamic test evidence, so `evidence[].sanitizer_runs` is
valid only on a `kind=test` item. Each run records `tool`
(`asan`/`ubsan`/`tsan`/`msan`/`lsan`), `build_flags`, `command`, `output`,
`output_sha256`, `exit_code`, `started_at`, `finished_at` and `status`, with an
optional `version`. `build_flags` is the instrumentation flag
(`-Zsanitizer=address` for Rust) because a run without it is
indistinguishable from an ordinary test run. L1 checks the shape, the tool and
status enums, the sha256 and the ISO timestamps. L2 verifies:

- `output` exists under `--tool-output-root` (default `--root`) and its SHA-256
  matches `output_sha256`;
- `finished_at`'s local date equals the evidence date, and `started_at` is not
  after it;
- `exit_code` is 0 and `status` is `completed` for a non-open claim: a
  cut-short or failed run is `unverified`/`failed`, not a pass with a short
  log (the V2-28 vocabulary is reused);
- a record that declares `completed` with exit 0 must not cite output that
  carries a finding line. The check matches the lines that halt a sanitizer:
  an optional process id followed by `ERROR: ` or `WARNING: ` and
  `AddressSanitizer:`, `LeakSanitizer:`, `UndefinedBehaviorSanitizer:`,
  `ThreadSanitizer:` or `MemorySanitizer:`, plus `SUMMARY: …Sanitizer:`. A
  bare sanitizer name in a test's expected string is not a finding. A
  recoverable UBSan `file:line: runtime error:` is deliberately not matched,
  because it can accompany exit 0.

The record does not prove that the build was instrumented, that the corpus
exercised the claim, or that the sanitizer would have caught a different
defect. `build_flags` is a declaration; a separately documented probe (for
example `nm <binary> | grep __asan_init`) is what shows the runtime is linked.
Without an external anchor a forger can rewrite the record and its output
together (C-13). A clean run is evidence that nothing fired in that corpus, not
proof that the claim holds.

## Fuzz run record

`fuzz-run.schema.json` describes what `tools/fuzz_run.py` writes (V2-17): the
target command, the oracle rules, the corpus manifest with a SHA-256 per seed,
the budget, the fixed seed, every finding with its input and captured log, and
`executions_digest`. The digest is the SHA-256 of the ordered input hashes, so
the same corpus and seed must reproduce it; a different corpus, budget or seed
is a different run. A `clean` verdict is scoped to that oracle and budget: the
adapter records a run it can replay, not the absence of bugs. See
`../spec/fuzz/README.md`.

## Fuzz triage

`fuzz-triage.schema.json` says what happens to each finding (V2-18). Every
finding in the record needs exactly one entry: `covered` (an existing cell,
detector and fixture already catch the failure class), `new` (no detector
caught it and those three artifacts now exist), or `not-a-bug` (the input
violates a documented contract, with the reason stated). A non-dismissal entry
names `cell`, `detector` and `fixture`, and the optional top-level `cells`
points at the registry they resolve against.

`tools/fuzz_triage.py` checks the shape (T1), one entry per finding with no
stale entries (T2), the cell and detector in that registry and the fixture ID
in the mutations file (T3), and that the record's verdict agrees with its
findings (T4). An empty triage is accepted only for a record with no findings.
The gate proves the artifacts exist, not that the routing decision was right.

## Checks

| Check | What it enforces |
| --- | --- |
| L1 | schema: required fields, ID format, unique IDs, enums, `kind=test` needs `tests`, `status=open` needs `limitations`, `run_record`, `tool_output`, `sanitizer_runs` and `shared_tests` shape and commit/command agreement, a non-empty `claims` array (an empty ledger cannot pass vacuously), `retired` tombstones with reasons and no live IDs |
| L2 | evidence health: artifact exists, commit resolvable, artifact matches its blob at the cited commit, dates within `--max-age-days` (default 90), run-record hashes and counts, tool-output hash, exit code and `status=completed` for a non-open claim (V2-28), sanitizer-run hash, exit code, `status=completed` and the finding-line contradiction (V2-35), cited tests appeared in the log |
| L3 | traceability: every test ID in `kind=test` evidence exists in the suite (`report("F8a ...")`, `def test_*`, or Rust `#[test] fn`) |
| L4 | consistency: status matches the strongest evidence channel; stronger evidence than status is a warning; `model-checked` and `proven` need a `tool_output`, `model-checked` also needs a bound |
| L5 | prose: unqualified absolutes in docs. Engine order: Vale (`styles/RussianAbsolutes` package) if the `vale` binary is available, fallback to the built-in line scanner |
| L6 | relevance: a test cited by two claims is declared in `shared_tests` with a reason by each of them, and a non-open claim cites at least one test no other claim cites (V2-34) |

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

- L1–L4 and L6: clean on 7/7 claims; evidence anchored to real commits
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
