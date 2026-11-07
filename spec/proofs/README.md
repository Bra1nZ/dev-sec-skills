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

This repository has no `proven` claim, but its
[`spec/proofs/manifest.yaml`](manifest.yaml) is no longer empty: it declares two
bounded checks for `tested` claims. P-01 is the agreement between an independent
model of the craft-i18n row grammar and `read_catalog`; P-02 is the mutation
control that shows the comparison can fail. A bounded check over a declared
vocabulary supports `tested`, not `model-checked`: agreement inside the
vocabulary is not a proof of the universal claim. The planner reads the
manifest, not the claim status, so a record that drifts is reported either way.

## Files

```text
spec/proofs/
  manifest.yaml                        # P-01/P-02: the C-02 bounded cross-check
  c02-bound-2026-11-07.md              # declared bound, space, decision rule, limits
  runs/
    c02-crosscheck-2026-11-07.json     # P-01 tool_output record
    c02-crosscheck-2026-11-07.log      # captured stdout, hash-checked
    c02-mutants-2026-11-07.json        # P-02 tool_output record
    c02-mutants-2026-11-07.log         # captured stdout, hash-checked
  README.md                            # this file
```

- `schemas/proof-manifest.schema.json` — the manifest's shape; every entry is
  rejected unless it names an artifact, a `tool_output` record, at least one
  `depends_on` path and at least one assumption.
- `crosscheck/c02-row-model/` — the independent model, the space generator and
  the mutation harness; see its `README.md` for the run commands. Build targets
  live under `/tmp/opencode/` and are disposable caches; the records and logs
  above are committed and do not depend on them.
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

## The first declared proofs

Both entries use the same crate and the same recorded run discipline.

| ID | Claim | Artifact | `tool_output` | Declared dependencies |
| --- | --- | --- | --- | --- |
| P-01 | C-38 | `crosscheck/c02-row-model/src/model.rs` | `spec/proofs/runs/c02-crosscheck-2026-11-07.json` | `crosscheck/c02-row-model/**`, the bound document, `tools/bounded_check.py` |
| P-02 | C-39 | `crosscheck/c02-row-model/src/main.rs` | `spec/proofs/runs/c02-mutants-2026-11-07.json` | the same set |

P-01 compares accepted rows and rejected line numbers with
`craft_i18n_tests::catalog::read_catalog` over 69,430 enumerated inputs. P-02
runs the same space once per one of 22 named model edits and requires each edit
to produce a divergence. The bound, the vocabulary and the decision rule are in
[`c02-bound-2026-11-07.md`](c02-bound-2026-11-07.md), written before the
recorded run.

C-38 and C-39 are claims in the CONCEPT registry
([`../conveyor/CONCEPT.md`](../conveyor/CONCEPT.md)); the pilot ledger has one
`kind: model-check` evidence item, on C-02 in
[`../pilots/craft-i18n/claims.yaml`](../pilots/craft-i18n/claims.yaml). The two
registries use the same ID shape but are separate namespaces: the pilot claim is
the row grammar of one crate, the CONCEPT claims are the cross-check and its
negative control.

The target's sources are not in this repository: the crate has a path
dependency on the craft-i18n checkout, and the checkout is pinned by
`crosscheck/c02-row-model/TARGET`. That produces a limit the manifest cannot
close by itself:

- A change to the target after the pinned commit is not a diff here, so it
  triggers no re-run. `claim_lint` L2 still compares the cited artifact
  (`crates/craft-i18n-tests/src/catalog.rs`) with its blob at the cited commit,
  which catches an artifact that moved but not a change to an uncited file.
- Changing `TARGET` is a declared `depends_on` change, so it does trigger a
  re-run; the re-run then fails or succeeds against the new checkout.
- `Cargo.lock` is declared because a dependency upgrade can change the target
  crate's behaviour without changing the target commit.

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

- `python3 tools/proof_plan.py --repo . --base a3293ec --head 4f3e25c
  --manifest spec/proofs/manifest.yaml` → `FRESH P-01`, `FRESH P-02`; summary
  `2 proof(s): 0 rerun, 2 fresh; 0 removed; 0 unmapped material; 9 changed
  file(s)`. Both records carry `record-covers-change`: their `finished_at` is
  later than the committer time of the model commit. `--require-fresh` exits 0
  on that range.
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

The limits above are the honest scope of that evidence: the eval suite is
synthetic; the mutation harness only proves the suite is sensitive to those
seven edits; P-01/P-02 are bounded checks over a declared vocabulary, not
proofs; a change to the target after the pin is invisible to the planner; and no
real re-run has yet been forced by a later change, so `record-covers-change` on
the first range is a timestamp outcome, not a demonstrated re-run.
