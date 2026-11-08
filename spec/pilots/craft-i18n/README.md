# Second pilot cell registry — `craft-i18n`

Date: 2026-11-06. Target: `/home/admini/projects/astraoffice/craft-i18n`,
HEAD `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` (working tree clean; the pilot
does not modify it). Registry: [`cells.yaml`](cells.yaml). Claims:
[`claims.yaml`](claims.yaml). Linter: `tools/cell_lint.py` (CL1–CL5) and
`tools/claim_lint.py` (L1–L7). Mutation fixtures:
[`mutations/`](mutations/README.md). Probe:
[`probes/invisible-characters/`](probes/invisible-characters/output.txt).

The first pilot (`rbac_pg`) was a PostgreSQL security extension: RBAC, MAC,
SQL, a live stand. This pilot is deliberately the opposite shape — a small
Rust crate that validates translation catalogs, with no database, no roles and
no server. The point is to test whether the cell taxonomy, the claim ledger and
the mutation gate generalise, not to audit `craft-i18n` for its own sake.

## Method

Cells were derived from detectors that already exist in the target:

- `docs/catalog-format.md` — the documented row, plural, `@msg`, locale and
  header rules;
- `crates/craft-i18n-tests/src/catalog.rs` — row parsing, escapes, placeholders,
  plural forms, `@msg` templates;
- `crates/craft-i18n-tests/src/tree.rs` — overrides, regional redundancy,
  language name, coverage report;
- `crates/craft-i18n-tests/src/locale.rs` — locale names and plural counts;
- `crates/craft-i18n-tests/tests/locales.rs` — the repository-wide and fixture
  trees the tests build.

Each cell names a property, the detector that enforces it, a claim where one
exists, and the residual risk. No cell was invented to fill a taxonomy class.

The claim ledger is authored here, not in the target, so the pilot leaves the
repository untouched. Its evidence points at the target's files and commit;
`claim_lint` is run with `--root` on the target and `--suite-glob` on the Rust
tests. This is the first ledger that resolves Rust `#[test] fn name` IDs; the
extractor (`RUST_TEST_RE`) and the per-case `suite_glob` in the linter evals
were added because of this pilot.

### Evidence policy

`tested` means a test detector exists and its suite has a recorded green
baseline. 12 of the 13 detectors also have a mutation fixture showing that the
detector fails when its mechanism is removed. CELL-013 carries a documented
`mutation_exemption`: it is a data-level check on the repository's own
`locales/`, and every source mutation that would make those catalogs fail also
fails the rule tests in the same suite. `open` means no detector exists.

Since 2026-11-07 every `kind=test` evidence item carries a `run_record`
(V2-02): the command, commit, exit code, timestamps, the SHA-256 of the log and
of the artifact, and the executed/passed counts. The captured log is
[`runs/cargo-test-2026-11-07.log`](runs/README.md) (26 tests, all passed).
`claim_lint` hashes the log and the source file it cites, checks that
`finished_at` belongs to the evidence date, and requires every cited test ID to
appear on a log line with a status. Re-dating the ledger or citing a test that
did not run now fails L2 without touching the target. L2 also compares each
cited artifact with its blob at `5c5c554`: a commit that resolves but predates
the bytes on disk fails as an unrelated commit, so moving the ledger's commit
field to an older point in the history does not make stale evidence look
verified.

The record is not proof of the run. Each `run_record` and the ASan run now
carry an SSH-signature anchor (C-41) over their canonical bytes, committed in
`spec/anchor/`, so editing a runner name, a hash or a timestamp after signing
fails L2. That narrows, but does not close, C-13: ten of these anchors were
created on 2026-11-08 over records dated 2026-11-07, so they prove the record
has not changed since signing, not when the run happened; and whoever can
replace `allowed_signers` and re-sign bypasses the check entirely. The pilot
records the limit rather than hiding it.

### Sanitizer run (V2-35)

C-02 also carries one ASan run as a separate `kind=test` evidence item: the
nightly `1.101.0` toolchain with `-Zsanitizer=address`, all 26 tests, exit 0,
and no finding line in the output. The log is
[`runs/asan-test-2026-11-07.log`](runs/README.md) and its `run_record` reuses
it, so the ledger has two independent runs of the same tests (stable and ASan).
L2 hashes the output, requires a completed exit-0 run, and rejects a record
that claims a clean run while its own output carries
`ERROR: AddressSanitizer:` or a `SUMMARY: …Sanitizer:` line. A clean ASan run
says the corpus did not trip the allocator with this instrumentation; it does
not prove the parser memory-safe. `std` is not instrumented, and the flag in
the record does not prove instrumentation by itself: the separate probe
[`runs/asan-instrumentation-2026-11-07.md`](runs/asan-instrumentation-2026-11-07.md)
records `__asan_init` in the executed binary. The red-team drill
`sanitizer-findings-hidden` confirms that the L2 contradiction check blocks a
hidden finding. C-02 stays `tested`; the sanitizer strengthens the evidence
but does not raise the status.

## Static-analysis channel (V2-36)

C-09 is the first claim in either pilot that is supported by `kind:
static-analysis` evidence. Semgrep 1.184.0 ran the three MIT rules authored in
[`spec/static-analysis/rules/`](../../static-analysis/rules/) over the target's
`.github/` at `5c5c554`, and the normalized report carries five findings:
two Dependabot update blocks without a `cooldown`, two mutable `uses:` refs
(`actions/checkout@v7`, a reusable workflow at `@main`) and one
`secrets: inherit`.

F-003 and F-004 are triaged `covered`; F-001, F-002 and F-005 are
`out-of-scope` with a reason. All five are real supply-chain hygiene gaps, and
this pilot's taxonomy is the translation-row grammar of
`docs/catalog-format.md`; no cell here owns that failure class. The two
mutable refs are instead routed across pilots to CELL-001,
D-PINNED-ACTIONS and MUT-001 in
[`spec/pilots/dev-sec-skills/`](../dev-sec-skills/cells.yaml), the self-pilot
registry. On 2026-11-08 the route was re-checked by running that detector
read-only over the craft-i18n workflow directory: it exits 1 and names
`ci.yml:17` and `sonarcloud.yml:20`. The target stays read-only, the detector
is not wired into its CI, and `new` was not available here.

The record is [`spec/static-analysis/`](../../static-analysis/README.md); the
claim is C-09. The rule set and both outputs are hashed, the report hashes the
same SARIF as an input, and `claim_lint` L2 checks the triage bijection. The
record proves that these findings came from this run, not that the target is
insecure or clean. The rule set is authored rather than vendored because the
Semgrep Registry `p/ci` rules are not redistributable.

## Lint result

```text
$ python3 tools/claim_lint.py \
    --root /home/admini/projects/astraoffice/craft-i18n \
    --suite-glob "crates/craft-i18n-tests/**/*.rs" \
    --run-log-root /home/admini/projects/dev-sec-skills \
    spec/pilots/craft-i18n/claims.yaml

ledger: spec/pilots/craft-i18n/claims.yaml | claims: 9
  L1 schema        OK
  L2 evidence      OK
  L3 traceability  OK
  L4 consistency   OK
  L5 prose         OK
total: 0 error(s), 0 warning(s), 0 info
```

```text
$ python3 tools/cell_lint.py \
    --root /home/admini/projects/astraoffice/craft-i18n \
    --ledger /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/claims.yaml \
    spec/pilots/craft-i18n/cells.yaml

registry: spec/pilots/craft-i18n/cells.yaml | cells: 14
  CL1 structure     OK
  CL2 coverage      0 error(s), 0 warning(s), 1 info
      [CL2] info  CELL-013 detector 'D-REPO' is exempt from a mutation fixture: ...
  CL3 evidence      OK
  CL4 traceability  OK
  CL5 taxonomy      OK
  CL6 escalation    OK
total: 0 error(s), 0 warning(s), 1 info
```

CL1, CL3, CL4, CL5 and CL6 are clean: fields are present, every artifact
path resolves inside the target, every detector's claim exists, no cell claims
more than its strongest detector, and no status moved against the base. CL2's
single info line is the CELL-013 exemption, not a warning. The CL6 run above
is against the commit that first contains the registry; before that commit the
gate explicitly reported a first-release skip.

CELL-003 is the first `runtime-enforcement` cell (V2-15/V2-16):
`kind: runtime-enforcement`, `negative_test: each_bad_row_is_one_problem`,
`enforced_at` = `parse_row` in `crates/craft-i18n-tests/src/catalog.rs:47`,
`oracle` = the test asserts exactly one problem per bad row prefixed `line N:`,
and `violation_response` = `read_catalog` returns the Problem and does not load
the row. `make verify` passes
`--suite-glob crates/craft-i18n-tests/**/*.rs`, so the ID resolves.

### Negative control

The clean run is not vacuous. Three mutations of the environment each exit
non-zero (run 2026-11-06):

```text
$ make lint-pilot2 PILOT2_ROOT=/nonexistent
error: pilot root not found: /nonexistent        # make exit 2

$ make lint-pilot2 BASE_REF=no-such-ref
error: base ref not found: no-such-ref           # make exit 2

$ make claims-pilot2 PILOT2_ROOT=/nonexistent
root not found: /nonexistent                     # make exit 2
```

The first proves the target is opened, not assumed. The second proves a typo in
the base ref fails instead of silently disabling the CL6 escalation gate — the
skip is allowed only when the ref resolves but the registry is absent at it
(the first-release state before this pilot was committed). The third exposed a
crash in `claim_lint`: it walked a nonexistent root and died with a traceback.
The tool now checks `--root` and exits 2 with a message.

`make verify` runs this pilot's three gates (`lint-pilot2`, `claims-pilot2`,
`status-pilot2`) after the `rbac_pg` gates. The ledger lives in this repository,
so the status gate diffs it against this repository's `BASE_REF`, not against
the target's history; on the commit that first contains the ledger the diff
reports `no status changes`.

## Mutation result

```text
BASELINE craft-i18n                       PASS  exit=0  failures=none
FIXTURE  MUT-001      CELL-001    D-CLEANROOM        PASS
...
FIXTURE  MUT-012      CELL-014    D-COVERAGE         PASS
fixtures: 12/12 matched
```

Details, the exact mutation per fixture and the known collateral failures are
in [`mutations/README.md`](mutations/README.md).

## Calibration

| Measure | Value |
| --- | --- |
| Cells | 14 |
| Non-open cells | 13 (all `tested`) |
| Open cells | 1 (CELL-002) |
| Detectors | 13 (`test`) |
| Detectors with a mutation fixture | **12 / 13** |
| Detectors with a documented exemption | 1 (CELL-013) |
| Cells linked to a claim | 14 / 14 |
| Claim ledger entries | 9 (C-01…C-09; C-08 is `open`, C-09 is `static-refinement`) |
| Duplicate `failure_class` values | none |

| Class | Cells |
| --- | --- |
| security | 2 |
| correctness | 11 |
| maintainability | 1 |

| Failure mode | Cells |
| --- | --- |
| detect | 14 |

Entry-point prefixes: `catalog` 11, `ci` 3, `locale-dir` 3, `locales` 1,
`report` 1.

## Cell map

| Cell | Property | Class | Status | Detector | Claim |
| --- | --- | --- | --- | --- | --- |
| CELL-001 | Every catalog declares clean-room provenance | security | tested | D-CLEANROOM | C-07 |
| CELL-002 | No invisible formatting character survives a translation | security | open | — | C-08 |
| CELL-003 | Wrong column count or empty field is rejected | correctness | tested | D-ROWS | C-01, C-02 |
| CELL-004 | Placeholders match the source text, in any order | correctness | tested | D-PLACEHOLDERS | C-03 |
| CELL-005 | Escapes limited to `\n`, `\t`, `\\`; CRLF/BOM tolerated | correctness | tested | D-ESCAPES | C-02 |
| CELL-006 | A key is defined once; context separates it | correctness | tested | D-UNIQUE | C-02 |
| CELL-007 | `@plural` lists the locale's CLDR form count | correctness | tested | D-PLURALS | C-04 |
| CELL-008 | Unmatchable `@msg` template is rejected | correctness | tested | D-MSG | C-03 |
| CELL-009 | App row identical to `common.tsv` is rejected | correctness | tested | D-OVERRIDE | C-05 |
| CELL-010 | Redundant regional row is rejected, with documented exceptions | correctness | tested | D-REGIONAL | C-05 |
| CELL-011 | Every locale names its language | correctness | tested | D-LANGNAME | C-07 |
| CELL-012 | Locale and catalog file names follow the layout | correctness | tested | D-NAMING | C-06 |
| CELL-013 | The repository's catalogs pass every rule | correctness | tested | D-REPO | C-01 |
| CELL-014 | Coverage report counts rows and never fails the build | maintainability | tested | D-COVERAGE | C-01 |

## Findings

### 1. The taxonomy generalises without new classes

14 cells fit into the existing `security`, `correctness` and `maintainability`
classes, with `detect` as the only failure mode. No RBAC, SQL or database
concept was needed; the same registry format, linter and mutation gate worked
unchanged on a Rust crate. The only tool changes were mechanical: resolving
Rust test IDs and letting an eval case use a Rust `suite_glob`. That is
evidence for the taxonomy, not a proof that it covers every domain.

### 2. One detector had a branch no test pins — and the pilot kept the result

The first draft of the D-NAMING mutation relaxed the app-file-name rule to
allow uppercase letters. The entire suite stayed green (26 passed). The rule
is enforced in source, but the only test for it, `bad_app_file_name`, uses
`Word_Craft.tsv`; the underscore is rejected by both the original and the
mutated predicate. The shipped fixture instead targets the locale-name branch,
where `locale_names` does flip. The untested branch is recorded as a
limitation of C-06 and CELL-012 — the pilot changed the fixture rather than
quietly dropping the finding.

### 3. A bundled test makes several cells share one failure

`each_bad_row_is_one_problem` bundles twenty malformed rows. Five different
mutations (placeholders, escapes, duplicate keys, plural count, `@msg`) all
flip it, so the fixture's expected set names it alongside the cell-specific
test. The cell map still separates the properties; the test does not. A
regression tells you the test name, not the rule.

### 4. The one open cell is a real defect, not a missing test

CELL-002 / C-08: `parse_row` rejects Cc control characters and U+FEFF, but
Unicode Cf formatting characters pass. The probe in
[`probes/invisible-characters/`](probes/invisible-characters/output.txt)
records U+202E (bidi override), U+200B (zero-width space) and U+2066
(left-to-right isolate) reaching the parsed row with no problem, while U+0007
and an embedded U+FEFF are rejected. A translator or a paste can therefore
make the UI render deceptively while every check stays green. No detector
exists; the cell is `open`, the claim is `open`, and nothing was upgraded to
look better.

### 5. 14/14 claim linkage is by construction

Unlike the first pilot (7 of 29 cells linked), every cell here links to a
claim. That is not a coverage achievement: the ledger was written for this
pilot in the same pass as the registry, so the linkage reflects how the pilot
was authored, not what the project tracks. The meaningful number is the linter
result and the mutation coverage.

### 6. The mutation gate needed two harness fixes to stay honest

Rust's test names are module-qualified (`catalog::tests::foo`), so the runner
normalises them before comparing sets. More seriously, sharing one
`CARGO_TARGET_DIR` across fixture copies made cargo reuse a mutated artifact
when a copy preserved the original mtime; the baseline check caught it and the
runner now copies with fresh mtimes. Both are recorded in
[`mutations/README.md`](mutations/README.md); a runner without the baseline
check would have reported a false pass.

## Limitations

- The pilot covers the checker's rules, not the apps' rendering, the runtime
  lookup in craft-libs, the translators' work, or the clean-room claim's
  truth. Those are named as residual risks or out of scope.
- The target's suite compares against CLDR 37 through `intl_pluralrules`,
  while the apps use CLDR 48. A locale whose categories changed between the
  two versions passes here and renders wrong; C-04 records this.
- The claim ledger lives in this repository, not in the target. It is evidence
  about the target at `5c5c554`, not a maintained artifact of the project.
- The probe is a manual artifact with a path dependency on the local checkout;
  it is not part of the target's CI.
- One baseline run and one mutation run were recorded on one machine
  (cargo 1.99.1). No flakiness study was done.
- The CELL-013 exemption is an argument, not a measurement: the cell is not
  mutation-verified on its own.
- C-09 measures the target's CI configuration, not its translation rows. Two
  findings are `covered` by the self-pilot's detector through a cross-pilot
  route, and three are `out-of-scope`; this pilot's taxonomy gained no
  supply-chain cell and no detector, and the detector is not wired into the
  target's CI. The rule set is authored here and is not the Semgrep `p/ci`
  benchmark.

## Reproduction

```bash
# claim ledger
python3 tools/claim_lint.py \
    --root /home/admini/projects/astraoffice/craft-i18n \
    --suite-glob "crates/craft-i18n-tests/**/*.rs" \
    --run-log-root /home/admini/projects/dev-sec-skills \
    --tool-output-root /home/admini/projects/dev-sec-skills \
    spec/pilots/craft-i18n/claims.yaml

# cell registry
python3 tools/cell_lint.py \
    --root /home/admini/projects/astraoffice/craft-i18n \
    --ledger spec/pilots/craft-i18n/claims.yaml \
    spec/pilots/craft-i18n/cells.yaml

# mutation fixtures (copies the target; never modifies it)
python3 spec/pilots/craft-i18n/mutations/run_mutations.py \
    --target /home/admini/projects/astraoffice/craft-i18n

# probe
cd spec/pilots/craft-i18n/probes/invisible-characters
CARGO_TARGET_DIR=/tmp/opencode/craft-i18n-target cargo run --offline -q
```

The static-analysis record is replayed from this repository, not from the
pilot:

```bash
# rerun the engine, then normalize (paths are relative to the rules directory)
cd spec/static-analysis/rules
semgrep scan --config ci-supply-chain-2026-11-07.yml --sarif \
    --output ../../static-analysis/runs/ci-craft-i18n-2026-11-07.sarif \
    --metrics off /home/admini/projects/astraoffice/craft-i18n

cd /home/admini/projects/dev-sec-skills
python3 tools/sarif_evidence.py --config spec/sarif/adapters.yaml --root . \
    --path-root /home/admini/projects/astraoffice/craft-i18n \
    --max-unmapped 0 --reject-fixtures \
    --json spec/static-analysis/runs/ci-craft-i18n-2026-11-07.report.json \
    spec/static-analysis/runs/ci-craft-i18n-2026-11-07.sarif
```

A rerun changes the SARIF bytes and therefore every hash in C-09; the record
and the claim are updated together or not at all.
