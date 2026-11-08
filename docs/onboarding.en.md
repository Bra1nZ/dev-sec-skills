# Bootstrap: install the gates in a foreign repository

A deterministic, idempotent run that copies the linters, writes honest `open`
registry and ledger templates, renders the CI templates and creates an
external signing key, then walks the first evidence record to green gates.

## Status and scope

- **Status:** `tested` (C-02), 2026-11-08. Evidence: a run of
  `spec/pilots/dev-sec-skills/detectors/test_bootstrap_eval.py`, which executes
  `evals/bootstrap/run_evals.py` against a throw-away git repository; the log
  and anchor live in `spec/pilots/dev-sec-skills/runs/`.
- **Scope:** Python 3.11, PyYAML, OpenSSH `ssh-keygen`, git; one synthetic
  target repository and a stdlib test suite. No product repository was
  exercised by that run.
- **What the run shows:** bootstrap creates the expected files, the templates
  pass `cell_lint` and `claim_lint`, the "run -> `run_record` -> anchor ->
  `tested`" path passes `cell_lint`, `claim_lint` and `status_diff`, and an
  edited vendor file, a changed signed field and a status escalation without
  evidence are caught.
- **What it does not show:** that the target test exercises the wording of the
  claim; that the private key is uncompromised; or that the CI template ran on
  a GitHub runner. C-13 stays `open`: the key holder can re-sign, and replacing
  `allowed_signers` together with a new signature bypasses the check. There is
  no transparency log, timestamping or key revocation.

## What `tools/bootstrap.py` does

It is a planner and generator, not a test runner. It:

1. copies `tools/{claim_lint,cell_lint,status_diff,anchor_subject,anchor_run}.py`,
   `styles/` and `schemas/` without their README files, and
   `spec/conveyor/cell-registry.schema.json`;
2. writes `tools/dev-sec-skills.VERSION` — JSON with the source commit, a
   dirty flag and the sha256 of every vendored file;
3. creates `spec/cells.yaml` and `docs/claims.yaml` with status `open`;
4. with `--with-ci`, renders `.github/workflows/{claim,cell}-lint.yml` from
   `ci/`, substituting the paths and `FIRST_RELEASE=1`;
5. with `--with-anchor`, creates or reuses an ed25519 key **outside** the
   repository and commits only the public half to
   `spec/anchor/allowed_signers`.

It does **not** run the target tests, write evidence or raise a status. The
`open` templates are a record shape, not coverage: creating a ledger says
nothing about the target code.

## Requirements

- Python 3.8+ and PyYAML: `pip install pyyaml`.
- `git` for `run_record.commit` and `status_diff`.
- `ssh-keygen` from OpenSSH for anchors.
- Optional Vale 3.26.0: when it is on `PATH`, `claim_lint` uses
  `styles/RussianAbsolutes`; otherwise the built-in scanner runs.

## Quick start

The target directory must exist. The command can run from any directory:
`--source` defaults to the checkout that contains the script.

```bash
python3 /path/to/dev-sec-skills/tools/bootstrap.py \
  --target ../my-service \
  --name my-service \
  --suite-glob 'tests/*.py' \
  --with-ci \
  --with-anchor
```

Useful variants:

```bash
# print the plan, write nothing
python3 tools/bootstrap.py --target ../my-service --dry-run

# refresh vendored linters after updating dev-sec-skills
python3 tools/bootstrap.py --target ../my-service --force

# a different key directory (default: ~/.config/dev-sec-skills/anchor)
DEV_SEC_SKILLS_ANCHOR_DIR=/secure/keys \
  python3 tools/bootstrap.py --target ../my-service --with-anchor
```

`--force` refreshes vendored `tools/`, `schemas/`, `styles/` and rendered CI
files. It **never** overwrites `spec/cells.yaml` or `docs/claims.yaml`: those
hold evidence, and a bootstrap that can erase evidence is a defect, not a
convenience.

## What lands in the target

```text
tools/
  claim_lint.py  cell_lint.py  status_diff.py
  anchor_subject.py  anchor_run.py
  dev-sec-skills.VERSION
styles/                      # no README.md
schemas/                     # no README.md
spec/
  conveyor/cell-registry.schema.json
  cells.yaml                 # one open cell, not coverage
  anchor/allowed_signers     # public keys only
docs/
  claims.yaml                # one open claim, evidence: []
.github/workflows/
  claim-lint.yml  cell-lint.yml   # only with --with-ci
```

Bootstrap prints a Makefile snippet (`make verify`, `make cells`,
`make claims`, `make status`) and a checklist. The snippet is a starting
point: substitute your `SUITE_GLOB` and your release ref.

## The first green run

The templates already pass, because the claim and the cell are honestly
`open`:

```bash
python3 tools/cell_lint.py --root . --ledger docs/claims.yaml \
  --suite-glob 'tests/*.py' spec/cells.yaml

python3 tools/claim_lint.py --root . --suite-glob 'tests/*.py' \
  --run-log-root . --tool-output-root . docs/claims.yaml
```

`cell_lint` may emit info about unused taxonomy classes; that is not an error.
`claim_lint` on the open template emits nothing.

## Promotion path

Order matters: artifact and run first, then the record, then the anchor, and
only then the status.

1. Replace `CELL-001` with a real invariant: `entry_points`, `failure_mode`,
   `residual_risk`, `limitations`. Keep `coverage_status: open` until a
   detector exists.
2. Replace `C-01` with a statement that a concrete test exercises. Keep
   `status: open` and `evidence: []`.
3. Run the test so the log names each test and ends with a machine-readable
   summary. For pytest: `pytest -v` (or `-rA`); for stdlib:
   `python3 -m unittest -v tests.test_smoke`.
4. Commit the log and compute the hashes:

   ```bash
   mkdir -p docs/runs
   python3 -m unittest -v tests.test_smoke \
     > docs/runs/unittest-2026-11-08.log 2>&1
   sha256sum docs/runs/unittest-2026-11-08.log tests/test_smoke.py
   git rev-parse HEAD
   ```

   The commit must contain the final artifact: `claim_lint` L2 compares the
   working file with its blob at the cited commit and fails when the file
   changed after it.
5. Add `evidence` with `kind: test`, `tests`, `command`, `artifact`, `commit`,
   `date` and `run_record`. A `run_record` requires `runner`, `command`,
   `commit`, `exit_code`, `started_at`, `finished_at`, `log`, `log_sha256`,
   `artifact_sha256`, `tests_run` and `tests_passed`. The date of
   `finished_at` must equal the evidence `date`.
6. Sign the record and paste the printed `anchor:` block into the
   `run_record`:

   ```bash
   python3 tools/anchor_run.py create \
     --ledger docs/claims.yaml --claim C-01 --channel run-record --run 0 \
     --key ~/.config/dev-sec-skills/anchor/key \
     --signer my-service-anchor-2026-11-08 \
     --out-dir spec/anchor \
     --allowed-signers spec/anchor/allowed_signers \
     --id run-record-my-service-c01-2026-11-08 --base .
   ```

7. Raise the claim `status` and the cell `coverage_status` to `tested`, add the
   detector to the cell, and commit the evidence, log, `spec/anchor/*.json*`
   and ledger changes together.
8. Run both linters and `status_diff`:

   ```bash
   python3 tools/status_diff.py --repo . --ledger docs/claims.yaml \
     --git-ref <base-ref> [--first-release]
   ```

`status_diff` allows `open -> tested` only when the claim gained a new
evidence entry; re-dating the same evidence does not support the escalation.

### About the log counters

`claim_lint` L2 compares `tests_run`/`tests_passed` with a pytest summary
(`N passed`) or a cargo summary. `unittest` prints `Ran N tests`, which the
linter does not parse: the record passes, but one `L2 info` remains ("counts
not cross-checked"). That is a visible limitation, not an error. Use pytest
with `-v` when the count cross-check matters.

## The key and `allowed_signers`

- The private key defaults to `~/.config/dev-sec-skills/anchor`; override it
  with `DEV_SEC_SKILLS_ANCHOR_DIR` or `--anchor-dir`.
- An `--anchor-dir` inside the target repository or inside the
  `dev-sec-skills` checkout is refused: the private key must not enter git.
- One key can serve several repositories. A signature is bound to the signer
  name and the channel namespace, so use a per-repository signer
  (`<name>-anchor-<date>`); `allowed_signers` is appended to, not rewritten.
- `--with-anchor` creates the key and commits the public half. Signing a
  record is a separate step (`anchor_run.py create`).
- Loss, rotation and revocation: `spec/anchor/README.md`.

## Vendoring and drift

`tools/dev-sec-skills.VERSION` is the single source of truth about the vendored
bytes. It records `source_commit`, `source_dirty` and the sha256 of every file.
On a second bootstrap:

- identical files are left untouched (mtime is preserved);
- an edited vendored file is reported as `DRIFT`, the command exits 1 and the
  file is **not** rewritten without `--force`;
- `--force` restores the source bytes, but never touches the registry or the
  ledger.

Do not patch a vendored linter in the target: a local edit disappears on the
next `--force`, and until then it disagrees with `VERSION`. Change the linter
in `dev-sec-skills`, commit there, then re-run bootstrap with `--force`.

The README files under `styles/` and `schemas/` are deliberately not vendored:
L5 scans `*.md` and would find the quoted banned words in them.

## CI templates

`--with-ci` renders two workflows from `ci/`:

- `claim-lint.yml` — L1–L5 over the ledger and `status_diff` against a release
  ref;
- `cell-lint.yml` — CL1–CL6 over the registry, with an optional ledger.

`LEDGER`, `REGISTRY`, `SUITE_GLOB` and `FIRST_RELEASE=1` are substituted.
`BASE_REF`/`RELEASE_REF` default to `v1.0`; after the first tag, set the real
ref and `FIRST_RELEASE=0`. `fetch-depth: 0` is required: `status_diff` reads
the base ledger from git.

The templates keep `actions/checkout@v4` and `actions/setup-python@v5`. Those
are mutable refs; pin them to a SHA before enabling the gate — exactly what
D-PINNED-ACTIONS checks in this repository. Bootstrap prints that warning and
does not pretend the template is already safe.

## What a green gate does not show

- An anchor fixes the bytes of a record, not its truth: the key holder can
  re-sign, and replacing `allowed_signers` plus a new signature bypasses the
  check (C-13).
- `claim_lint` checks hashes, the commit, the date and that the test appears in
  the log; it does not check that the test exercises the claim. That stays a
  review question.
- `cell_lint` checks shape and links, not that the detector catches the stated
  failure. `security` and `correctness` cells need a mutation fixture; a
  documented `mutation_exemption` is a statement, not a check.
- L5 checks prose. It does not make a statement true and does not replace
  evidence.
- The bootstrap eval is synthetic: one temporary repository, stdlib tests,
  Linux. Other runners, Windows and real product repositories are not covered.

## Self-check

```bash
python3 evals/bootstrap/run_evals.py   # 4/4
make evals                             # includes bootstrap-eval
make detectors-self                    # D-BOOTSTRAP over the same eval
```

The eval checks: file creation and `VERSION` hashes; idempotency; drift
detection and `--force` recovery; green open gates; the full path to `tested`
with an anchor; that `--force` does not overwrite the ledger; failure on a
changed signed field; failure of `status_diff` on an escalation without
evidence; refusal of a target inside the source and of a key inside the
target.

## Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| `PyYAML is required` | dependency missing | `pip install pyyaml` |
| `ssh-keygen is required` / `not found` | no OpenSSH | install `openssh-client` |
| `DRIFT tools/...` | a vendored file was edited | review it; `--force` restores the source |
| `artifact ... does not exist at the cited commit` | the commit predates the file | commit the artifact and cite that commit |
| `artifact ... changed after the cited commit` | the file changed after the run | run again and commit again |
| `finished_at date ... does not match evidence date` | different dates | align `date` and the `finished_at` date |
| `test ... is cited but not executed in the run log` | the log does not name the test | `pytest -v` / `unittest -v`, recapture the log |
| `counts ... disagree with log` | counters do not match the summary | recompute `tests_run`/`tests_passed` |
| `anchor subject does not describe this record` | a field changed after signing | revert or re-sign |
| `not found in suite` | `--suite-glob` misses the file | widen the glob, not to the whole repository |
| `CL2 ... has no mutation_fixture` | security/correctness without a fixture | add a fixture or a documented exemption |
| `L2 info ... counts not cross-checked` | the runner has no recognized summary | use pytest `-v`, or accept the limitation |

## Related documents

- `spec/conveyor/CONCEPT.md` — V2-38, C-13, C-02.
- `spec/anchor/README.md` — keys, rotation, loss.
- `spec/static-analysis/README.md` — the static-analysis channel.
- `ci/claim-lint.yml`, `ci/cell-lint.yml` — source templates.
- `spec/pilots/dev-sec-skills/` — the self-pilot registry, ledger and detectors.
