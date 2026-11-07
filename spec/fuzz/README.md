# Fuzz Runs

`tools/fuzz_run.py` (V2-17) runs a command over a seed corpus and over inputs
mutated from that corpus with a fixed seed, checks every execution against an
explicit oracle, and writes one JSON record. The record is the artifact: it
names the oracle, the corpus manifest, the budget, the seed, and every failing
input with its captured output.

This is not a coverage-guided fuzzer. Mutations are random edits and the record
says so. The adapter exists so that a fuzz run has an oracle, a budget, a fixed
seed and a replayable artifact instead of a terminal session nobody can
reconstruct.

## Files

```text
spec/fuzz/
  corpus/claim-lint/                    # five seed ledgers for the real run
  runs/claim-lint-2026-11-07.json       # the recorded run (verdict: clean)
```

- `schemas/fuzz-run.schema.json` — the record's shape.
- `evals/fuzz/` — 5 adversarial cases for the adapter.
- `make fuzz-claim-lint` — replay the record and compare `executions_digest`.

## Oracle rules

A run is a finding when any rule matches; the rules are OR-ed.

| Rule | Fires when |
| --- | --- |
| `exit:N` | the exit code is not `N` |
| `exit-not-in:N,M,...` | the exit code is not in the list |
| `stdout-contains:TEXT` | `TEXT` appears in stdout |
| `stderr-contains:TEXT` | `TEXT` appears in stderr |
| `timeout` | the execution exceeded `--timeout` |

The target is split with `shlex` and run without a shell. `@INPUT@` in the
target is replaced by the input path (when absent the path is appended), and the
same bytes go to stdin.

## The recorded run

Run on 2026-11-07 against `tools/claim_lint.py` at commit `35b3675`:

```text
seed 20261107, 150 mutated runs, 5 seeds, 155 executions, verdict clean
oracle: stderr-contains:Traceback (most recent call last)
        exit-not-in:0,1,2
record: spec/fuzz/runs/claim-lint-2026-11-07.json
executions_digest: 93e1af3183658aa6…
```

Both oracle rules are deliberate:

- `stderr-contains:Traceback` catches an uncaught exception. A crash is a
  defect even when the exit code is in the allowed set, so the exit rule alone
  would miss it.
- `exit-not-in:0,1,2` allows 2 because `claim_lint` documents exit 2 as a
  usage or parse error. A mutated ledger that is not valid YAML is expected to
  exit 2; treating it as a finding would report every broken seed as a bug and
  the signal would be lost. Exit 1 means findings or errors, exit 0 clean;
  anything else is unhandled.

The committed record validates against `schemas/fuzz-run.schema.json` (draft-07,
checked with `jsonschema`; 0 errors). The corpus is five ledger shapes: a valid ledger, an `open` claim, an empty
`claims` array, a scalar instead of a document, and a ledger with a tombstone.
The run's clean verdict means the adapter saw no unhandled exit code and no
traceback across those shapes and 150 mutations. It does not mean `claim_lint`
is free of bugs: a random mutator explores a tiny fraction of the input space,
and this oracle only observes crashes and unexpected exits, not wrong verdicts.

## Determinism

The corpus is read in sorted path order and the mutator is
`random.Random(seed)`. `executions_digest` is the SHA-256 of the ordered input
hashes, so the same corpus and seed must reproduce it. The record's digest was
first produced by a trial run before the record was written to the repository,
and `make fuzz-claim-lint` replays the committed corpus and seed and compares the
two digests; a mismatch exits 1.

Measured negative control: replaying with a changed budget (`--runs 0`) or a
changed corpus produces a different digest, the digest check exits 1 and make
reports failure, so the comparison is not vacuous.

## What a clean record does not prove

- It does not prove the target is correct, or that a wrong verdict was not
  produced. The oracle only sees the exit code and the two markers above.
- It is scoped to this corpus, this seed and this budget. A different seed is a
  different run and needs its own record.
- The digest binds the inputs, not the target's behaviour. It proves the same
  inputs were generated; the captured logs of findings are what show what the
  target did on them.
- The replay is not part of `make verify`: it executes the target 155 times
  (about a minute), which is too slow for a merge gate. `make verify` runs the
  5 adapter evals in `evals/fuzz/`.
