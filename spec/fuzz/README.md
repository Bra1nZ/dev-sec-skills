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
  runs/claim-lint-2026-11-08-schedule.json  # downloaded CI artifact of the first scheduled replay
  triage/claim-lint-2026-11-07.yaml     # triage of that run (no findings)
```

- `schemas/fuzz-run.schema.json` — the record's shape.
- `schemas/fuzz-triage.schema.json` — the triage's shape.
- `evals/fuzz/` — 5 adversarial cases for the adapter.
- `evals/fuzz-triage/` — 13 adversarial cases for the triage gate.
- `make fuzz-claim-lint` — replay the record and compare `executions_digest`.
- `make check-fuzz-triage` — T1–T4 over the record and its triage file.

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
checked with `jsonschema`; 0 errors). The corpus is five ledger shapes: a valid
ledger, an `open` claim, an empty `claims` array, a scalar instead of a
document, and a ledger with a tombstone.
The run's clean verdict means the adapter saw no unhandled exit code and no
traceback across those shapes and 150 mutations. It does not mean `claim_lint`
is free of bugs: a random mutator explores a tiny fraction of the input space,
and this oracle only observes crashes and unexpected exits, not wrong verdicts.

## The first scheduled replay (2026-11-08)

The nightly workflow fired for the first time on 2026-11-08 as run
[42466635404](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42466635404):
`event: schedule`, commit `7bf8192`, started `09:18:42Z` and finished
`09:19:01Z`, conclusion `success`. The declared cron is `02:30Z`, so GitHub
started the job 6h49m late; the timer is wired, but its clock is not a
guarantee. The log line `recorded digest: 93e1af3183658aa6 | replay digest:
93e1af3183658aa6` is the gate passing.

The artifact `fuzz-record-42466635404` was downloaded and committed unchanged
as `runs/claim-lint-2026-11-08-schedule.json` (sha256 `8ca3fcb9…`, `verdict:
clean`, seed 20261107, 155 executions, 0 findings). It validates against
`schemas/fuzz-run.schema.json`.

That file is a downloaded CI artifact, not a locally executed run: its `cwd` is
the runner's checkout, and it shows what the hosted runner computed. It is not
anchored — C-41 covers three evidence channels and a fuzz record is not one of
them — so it can be fabricated like any unanchored record; the external copy is
the GitHub artifact, which expires after 90 days. One successful schedule shows
the timer fires; it does not show that a delayed or skipped run would be
noticed, because nothing alerts on it.

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

## Triage

A finding that stays in a JSON artifact disappears after the run. V2-18 makes
each one an entry in a triage file next to the record, and `tools/fuzz_triage.py`
fails the repository when an entry is missing or points at nothing:

| Disposition | Meaning | Required |
| --- | --- | --- |
| `covered` | an existing cell, detector and fixture already catch this failure class | `cell`, `detector`, `fixture` |
| `new` | nothing caught it; the cell, detector and fixture now exist | `cell`, `detector`, `fixture` |
| `not-a-bug` | the input violates a documented contract, so the finding is the contract working | `reason` |

The gate checks T1 shape, T2 one entry per finding (an untriaged finding, a
duplicate entry and a stale entry are errors), T3 that the cell and detector
resolve in the registry named by the triage file and the fixture ID exists in
the mutations file, and T4 that the record's verdict agrees with its findings.

The committed run has no findings, so its triage file has no entries. That is
the complete triage of a clean run, not a skipped one, and it is the only case
where an empty file is accepted: the moment the record gains a finding, the
same command fails until the entry and the three artifacts exist. A negative
control was measured by injecting a finding into a copy of the record in `/tmp`
(the repository artifact was not touched): the gate exited 1 with
`finding has no triage entry`.

Limits: the gate proves the named artifacts exist, not that `covered` was the
right call over `new` — that is a review judgment. It has not yet run on a real
finding, because the recorded run is clean; the 13 eval cases are synthetic and
say so.

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
  adapter and triage evals (`evals/fuzz/`, `evals/fuzz-triage/`) and the triage
  gate over the committed record.
