# Two-engine SARIF run — measurement for C-08

C-08 says an engine-agnostic ensemble through SARIF adapters can cover cells
"in minutes", but until now only one engine had produced a real run and no
wall-clock number existed. This record is the measurement, not a coverage
claim: it shows that two real engines, two different rule sets and one
normalizer produce one report quickly. The findings were triaged on 2026-11-08
in a separate ledger (C-40, `spec/pilots/rbac_pg/analysis-claims.yaml`), and
that triage put none of them in a cell, so C-08 stays `open`: the ensemble is
fast, but the cells are still untouched by it.

## Target and engines

| Field | Value |
| --- | --- |
| Target | `/home/admini/projects/rbac_pg/setup` |
| Commit | `d97860929b40a7a1f65e7b6a8cef66e72ef1cf4f` |
| Engine 1 | Bandit 1.9.4 (`-t B608,B105,B602`) |
| Engine 2 | Semgrep OSS 1.184.0, `python-audit-2026-11-07` |
| Semgrep rules SHA-256 | `26b192da07ca79599816a00c1d543487d7fd91b2f876afa3f3e786783e3aab85` |
| Bandit rules | built-in B608, B105, B602; no external rule file |
| Prepared artifacts | `runs/rbac-pg-bandit-2026-11-07.sarif`, `runs/rbac-pg-semgrep-2026-11-07.sarif`, `runs/rbac-pg-two-engine-2026-11-07.report.json` |

Bandit 1.9.4 does **not** write SARIF by itself: `-f sarif` is rejected with
`invalid choice: 'sarif' (choose from 'csv', ..., 'yaml')` unless the separate
`bandit-sarif-formatter` package (measured version 1.1.1) is installed next to
it. The 2026-11-08 re-run confirms this: the first attempt exited 2 with that
message, and after installing the formatter the same command exited 0. An
earlier revision of this document said the opposite; that statement was not
measured and is wrong. Both engines were installed under `/tmp/opencode`
because `/home` is nearly full and `python3 -m venv` is unavailable on this
machine. That prefix is rebuildable and is not evidence; the committed SARIF
and report are.

## Commands and measured time

Timing used `date +%s.%N` immediately before and after each command. The
commands are the ones that wrote the committed artifacts.

| Step | Command (short) | Start | End | Wall clock |
| --- | --- | --- | --- | --- |
| Bandit | `python3 -m bandit -t B608,B105,B602 -f sarif -r setup` | `23:44:11+03:00` | `23:44:13+03:00` | 2.280 s |
| Semgrep | `semgrep scan --config python-audit-2026-11-07.yml ... setup` | `23:44:13+03:00` | `23:44:21+03:00` | 7.240 s |
| Normalize + gate | `sarif_evidence.py --require-engines 2 --max-unmapped 0` | `23:44:24+03:00` | `23:44:25+03:00` | 0.498 s |
| **Total** | three commands | | | **10.018 s** |

Bandit exits 1 when it has findings; that is the engine's convention, not a
failed run, and this run did exit 1. The 2026-11-08 re-run added `--exit-zero`
so the record's `exit_code` is a measured 0 rather than a reinterpreted 1; the
finding set did not change. The adapter does not reinterpret the code. Because
the result cannot support a non-open claim without that adapter, C-08 stays
`open`.

Semgrep ran from `spec/static-analysis/rules` with a relative `--config`; an
absolute path prefixes every rule ID with the path and breaks the adapter
mapping.

## What the report contains

| Metric | Value |
| --- | --- |
| Inputs | 2 |
| Engines present | 2 (`bandit`, `semgrep`) |
| Findings | 249 |
| By engine | Bandit 63, Semgrep 186 |
| Mapped | 249 |
| Unmapped | 0 |
| Duplicates | 0 |
| Fixture inputs | 0 |
| Findings with a cell | 0 |
| Report digest | `6ebf84561298157750adab39b3c41e9d18c5b16d24bdaf51bdd75af3e10352f8` |

Bandit's B608 (49) and the authored Semgrep rule (186) name the same failure
class, `invalid-or-injected-input`; 38 source lines are reported by both
engines. Neither resolves to a cell. An earlier revision of the adapter mapped
both to `rbac_pg/CELL-010`, but that cell's `failure_class` is
`input-validation`, so the mapping claimed a class the cell does not own. The
mapping was removed and the loader now rejects such a mismatch (exit 2); every
finding in this report keeps `cell: null`. B105 (14) maps to
`exposed-secret-or-weak-crypto` with no cell. B602 produced no findings on this
target. The digest changed with the adapter revision: the normalized finding
carries the `cell` field.

Revision note (2026-11-08): the adapter's cell mappings were class-only before
this report was regenerated; the two SARIF inputs and the engines' output are
unchanged.

## Re-run and triage (2026-11-08)

The combined report above answers C-08's question and stops there. Triaging it
needs a different shape: a static-analysis record's `triage` is a bijection
with *one* report's findings, and the record hashes one engine's output. Both
engines were therefore re-run into separate per-engine records on 2026-11-08,
and every finding got a disposition in
`spec/pilots/rbac_pg/analysis-claims.yaml` (claim `C-40`).

| Field | Bandit | Semgrep |
| --- | --- | --- |
| Engine | Bandit 1.9.4 (+ `bandit-sarif-formatter` 1.1.1) | Semgrep OSS 1.184.0 |
| Selector / rules | built-in `B608,B105,B602`, manifest `rules/bandit-builtin-2026-11-08.yaml` | `rules/python-audit-2026-11-07.yml` |
| Rules SHA-256 | `d9201513dcca8178653003e4b35a11a7f0bf8c34c0738dd2aae9835686b5923e` | `26b192da07ca79599816a00c1d543487d7fd91b2f876afa3f3e786783e3aab85` |
| SARIF SHA-256 | `e59fa28061cebfabb15cbc0d38513300387247ad954ac35c8e51abb6d9be8d34` | `a850a7500db0fc2b25a3fa575e3f3811d4f633e6787bda92f467e6d6421082e8` |
| Report SHA-256 | `8185cf353e4555ae0224ec70164fc2f5d6213ce740555d29fa96a5cf1d001552` | `036733d725653a3c8bc6648c213c3d140af717c9763d402ba8c5d58be40e5284` |
| Started | `2026-11-08T14:06:53+03:00` | `2026-11-08T14:07:06+03:00` |
| Finished | `2026-11-08T14:06:59+03:00` | `2026-11-08T14:07:24+03:00` |
| Exit code | 0 (`--exit-zero`) | 0 |
| Findings | 63 | 186 |
| Unmapped / fixtures | 0 / 0 | 0 / 0 |
| Digest | `ad5199dac229e8d1…` | `5f1a53f685a46914…` |
| Anchor | `rbac-pg-bandit-2026-11-08` | `rbac-pg-semgrep-2026-11-08` |

What changed against the 2026-11-07 run, measured rather than assumed:

- The Semgrep SARIF is byte-identical to `rbac-pg-semgrep-2026-11-07.sarif`
  (same SHA-256), so that record's 186 findings are the same bytes.
- The Bandit SARIF differs from `rbac-pg-bandit-2026-11-07.sarif` in exactly
  one line, `endTimeUtc`; the 63 normalized findings are identical and the
  digest is unchanged.
- The Bandit exit code moved from 1 to 0 only because `--exit-zero` was added.
  Findings were not suppressed: the count and the digest are the same.

The 249 decisions are all `not-a-bug`. That is a measurement, not a
preference: `spec/pilots/rbac_pg/cells.yaml` owns no cell whose `failure_class`
is `invalid-or-injected-input` or `exposed-secret-or-weak-crypto`, so there was
nothing to route to. The reasons were assigned by mechanism over 23 files and
211 distinct `(path, line)` sites — 38 sites are reported by both engines —
using `spec/pilots/rbac_pg/triage_2026-11-08.py`, whose GROUP/SITE tables name
the definition, line and call sites behind each interpolation. The classes are
`const`, `loop`, `param`, `catalog`, `generated`, `env`, `nointerp`, `escaped`,
`percent_const`, and three B105 shapes (shared test secret, role password,
environment-variable name). Every reason and its `path:line` note are in the
ledger; this document does not repeat them.

`not-a-bug` here says that no request, argument or database value reaches the
cited statement in that harness. It does not say the statement would stay safe
if the harness took request data. A real injection in production code would be
`out-of-scope` for this registry rather than `covered`, and none was found.

## What it proves and what it does not

It proves that two real engines with different rule vocabularies normalize
into one report in about ten seconds, that both are present in the report, and
that the `--require-engines 2` and `--max-unmapped 0` gates can both pass on
real output. It does not prove that the ensemble covers the cells: no finding
was triaged `covered` or `new`, and the 249 entries are a review queue whose
every entry is now decided but none is routed. The Semgrep rule is one authored
text rule (MIT), not a benchmark rule set; a different rule set changes the
queue. Bandit's analysis is pattern-based, not data flow. The target is
read-only, so nothing was fixed and no detector was added. The 2026-11-08
per-engine records and their triage are anchored (C-41); the 2026-11-07
combined report and its two SARIF files are not. The two Bandit SARIF files
differ in exactly one line (`endTimeUtc`), so the 2026-11-07 finding set is the
same as the committed 2026-11-08 one; the 2026-11-07 file itself still carries
SHA-256 `f94c0ca8…`.


## Reproduce

```bash
cd /home/admini/projects/rbac_pg
PYTHONPATH=/tmp/opencode/bandit-site python3 -m bandit \
  -t B608,B105,B602 -f sarif -r setup -q \
  -o /home/admini/projects/dev-sec-skills/spec/static-analysis/runs/rbac-pg-bandit-2026-11-07.sarif

cd /home/admini/projects/dev-sec-skills/spec/static-analysis/rules
PATH=/tmp/opencode/semgrep-site/bin:$PATH \
PYTHONPATH=/tmp/opencode/semgrep-site SEMGREP_SEND_METRICS=off \
semgrep scan --config python-audit-2026-11-07.yml --sarif \
  --output ../../static-analysis/runs/rbac-pg-semgrep-2026-11-07.sarif \
  --quiet --disable-version-check --metrics off /home/admini/projects/rbac_pg/setup

cd /home/admini/projects/dev-sec-skills
python3 tools/sarif_evidence.py --config spec/sarif/adapters.yaml --root . \
  --path-root /home/admini/projects/rbac_pg \
  --max-unmapped 0 --reject-fixtures --require-engines 2 \
  --json spec/static-analysis/runs/rbac-pg-two-engine-2026-11-07.report.json \
  spec/static-analysis/runs/rbac-pg-bandit-2026-11-07.sarif \
  spec/static-analysis/runs/rbac-pg-semgrep-2026-11-07.sarif
```

The two per-engine records of 2026-11-08 (the ones the triage hashes):

```bash
# Bandit: --exit-zero so the record's exit_code=0 is measured, not reinterpreted
cd /home/admini/projects/rbac_pg
PYTHONPATH=/tmp/opencode/bandit-site python3 -m bandit \
  -t B608,B105,B602 -f sarif -r setup -q --exit-zero \
  -o /home/admini/projects/dev-sec-skills/spec/static-analysis/runs/rbac-pg-bandit-2026-11-08.sarif

cd /home/admini/projects/dev-sec-skills/spec/static-analysis/rules
PATH=/tmp/opencode/semgrep-site/bin:$PATH \
PYTHONPATH=/tmp/opencode/semgrep-site SEMGREP_SEND_METRICS=off \
semgrep scan --config python-audit-2026-11-07.yml --sarif \
  --output ../../static-analysis/runs/rbac-pg-semgrep-2026-11-08.sarif \
  --quiet --disable-version-check --metrics off /home/admini/projects/rbac_pg/setup

cd /home/admini/projects/dev-sec-skills
for engine in bandit semgrep; do
  python3 tools/sarif_evidence.py --config spec/sarif/adapters.yaml --root . \
    --path-root /home/admini/projects/rbac_pg \
    --max-unmapped 0 --reject-fixtures \
    --json spec/static-analysis/runs/rbac-pg-$engine-2026-11-08.report.json \
    spec/static-analysis/runs/rbac-pg-$engine-2026-11-08.sarif
done

# the triage is generated, then checked against the report by L2
python3 spec/pilots/rbac_pg/triage_2026-11-08.py \
  --bandit spec/static-analysis/runs/rbac-pg-bandit-2026-11-08.report.json \
  --semgrep spec/static-analysis/runs/rbac-pg-semgrep-2026-11-08.report.json \
  --out /tmp/opencode/triage.yaml
make claims-static-rbac
```

The `PYTHONPATH` prefix must contain both `bandit` and `bandit_sarif_formatter`;
without the formatter the command exits 2 instead of writing SARIF.
