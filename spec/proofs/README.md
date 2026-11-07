# Proof Manifest

A `proven` claim is a statement about specific bytes: a model, the code that
model abstracts, the encoding that fixes what the model means, and the tooling
that translates one into the other. Change any of those and the proof describes
something that no longer exists. `tools/proof_plan.py` (V2-29) reads a manifest
that declares those dependencies, compares a git range against them, and says
which proofs must be re-run.

The reason this is a planner and not a rule is cost. Re-running every proof on
every pull request makes proofs expensive enough to be dropped; running none
lets a proof quietly describe dead code. A diff decides, and the decision is a
record with reasons, not a convenient silence.

This repository currently has **no `proven` claim**, so
[`spec/proofs/manifest.yaml`](manifest.yaml) is empty. An empty manifest is a
declaration of absence, not coverage: with `--require-fresh` the planner prints
that the gate is vacuous instead of returning a green run that looks like proof
coverage.

## Files

```text
spec/proofs/
  manifest.yaml                        # empty: no claim is `proven` yet
  README.md                            # this file
```

- `schemas/proof-manifest.schema.json` — the manifest's shape; every entry is
  rejected unless it names an artifact, a `tool_output` record, at least one
  `depends_on` path and at least one assumption.
- `tools/proof_plan.py` — the planner, read-only on the target repository.
- `evals/proof-plan/run_evals.py` — 36 synthetic git scenarios.
- `evals/proof-plan/mutation_selftest.py` — eight mutants of the planner, each
  required to turn a named scenario red.
- `make proof-plan` — resolve the merge base of `origin/main..HEAD` and print
  the plan for this repository.
- `make proof-plan-selftest` — run the mutant harness (~80 s, not in `verify`).

## What triggers a re-run

| Trigger | Declared in | Why it invalidates a record |
| --- | --- | --- |
| `dependency-changed` | `depends_on` | The code the model abstracts moved. |
| `dependency-changed` | `artifact`, `model` | The model itself changed. |
| `dependency-changed` | `encoding` | The same model over a different configuration is a different question. |
| `dependency-changed` | `tooling` | A changed translator or checker wrapper can change the verdict with model and code untouched. |
| `manifest-changed` | `--manifest-base` | The proof's scope or assumptions moved, so the old record describes the old definition. |
| `proof-added` | `--manifest-base` | A new entry has no covering record. |
| `record-not-completed` | `tool_output` | `unverified`, `failed`, `error` or a missing `status` proves nothing, even when nothing changed. |
| `all` | `--all` | A scheduled full run. |

`depends_on` accepts globs: `*` matches within one path segment, `**` crosses
segments. Renames are matched through the old path as well, so moving a file
out of a declared path is still a change. A deleted dependency is a change.
A changed file that maps to no entry *and* looks like proof material
(`.tla`, `.smt2`, `.als`, `.lean`, `.dfy`, …, see `MATERIAL_EXTENSIONS`) is
reported as `unmapped`, which is a gap in the manifest, not a pass.

## How freshness is decided

A record covers a change when both hold:

1. `status` is exactly `completed`;
2. `finished_at` is at or after the committer time of the newest commit in
   `base..head` that touched a declared path.

Anything else is `rerun`. There is no "probably fine": a missing `finished_at`
is `rerun`, a timestamp that only equals the change time is still `fresh`
(`>=`), and a record one second older is not.

This is a timestamp comparison, and its limits are real:

- The planner cannot tell which checkout the runner actually loaded. A record
  produced after the change, from a stale tree, looks fresh.
- Committer time is used, not author time; rebases and amended commits move it.
- Clock skew between the runner and the machine that committed is invisible.
- The record's hash is not verified here. `claim_lint` L2 does that. Nothing
  verifies that the checker's semantics match what the claim says.
- The manifest is the scope. A shared helper that a proof uses indirectly and
  the manifest omits is invisible. `--require-complete` only catches changed
  files that look like proof material; it cannot see semantics.
- Paths resolve relative to `--repo` (absolute paths are allowed, but nothing
  fetches a remote model repository).

## Gates and exit codes

| Flag | Fails when | Exit |
| --- | --- | --- |
| — | plan produced | 0 |
| `--require-fresh` | any proof is `rerun` | 1 |
| `--require-complete` | any changed proof material is unclaimed | 1 |
| both | either condition | 1 |
| — | git, manifest or reference error | 2 |

`--base` must be a merge base, not the base branch tip; the caller resolves it
(`make proof-plan` does). A manifest whose `artifact` does not exist, whose
record is missing or is not JSON, whose `depends_on` is empty, whose assumptions
are unstated, or that carries an unknown key is an input error (2), not a stale
proof: a manifest
that points at nothing is broken, and a proof whose assumptions are unwritten
is an overclaim.

The eval cases pin the gates directly: stale vs covered, the timestamp
boundary, a non-completed record with no other change, a rename and a delete of
proof material, an empty manifest under both gates, and the input errors. The
runner prints every case name, so the list is the file, not this paragraph.

## Evidence

Measured 2026-11-07 on this repository:

- `python3 evals/proof-plan/run_evals.py` → 36/36 cases pass.
- `python3 evals/proof-plan/mutation_selftest.py` → 8/8 mutants caught, each by
  a case named for the mutated behaviour: strict freshness, ignoring the old
  path in material detection, moving the record-status gate inside the reasons
  branch, treating a manifest change as fresh, ignoring renames in dependency
  matching, a no-op `--require-complete`, `--all` returning `fresh`, and an
  ignored unknown manifest key.
- A demo manifest in `/tmp` (not committed, and its artifact is a Python file,
  not a model) run against the real range `a50fbda..HEAD` produced
  `RERUN P-01 record-predates-change` and `FRESH P-02`; the same range with
  `--require-fresh` exited 1, and the docs-only commit `02be7ab~1..02be7ab`
  exited 0.

The limits above are the honest scope of that evidence: the scenario suite is
synthetic, the mutation harness only proves the suite is sensitive to those
seven edits, and no real proof has ever been planned in this repository
because no claim is `proven`.
