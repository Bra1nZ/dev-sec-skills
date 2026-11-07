# Two-engine SARIF run — measurement for C-08

C-08 says an engine-agnostic ensemble through SARIF adapters can cover cells
"in minutes", but until now only one engine had produced a real run and no
wall-clock number existed. This record is the measurement, not a coverage
claim: it shows that two real engines, two different rule sets and one
normalizer produce one report quickly. It does not triage the findings, so
C-08 stays `open`.

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

Bandit 1.9.4 writes SARIF itself (`-f sarif`); the separately installed
`bandit-sarif-formatter` package was not needed. Both engines were installed
under `/tmp/opencode` because `/home` is nearly full and `python3 -m venv` is
unavailable on this machine. That prefix is rebuildable and is not evidence;
the committed SARIF and report are.

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
failed run. The adapter does not reinterpret the code. Because the result
cannot support a non-open claim without that adapter, C-08 stays `open`.

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

## What it proves and what it does not

It proves that two real engines with different rule vocabularies normalize
into one report in about ten seconds, that both are present in the report, and
that the `--require-engines 2` and `--max-unmapped 0` gates can both pass on
real output. It does not prove that the ensemble covers the cells: no finding
was triaged `covered` or `new`, and the 249 entries are a review queue. The
Semgrep rule is one authored text rule (MIT), not a benchmark rule set; a
different rule set changes the queue. Bandit's analysis is pattern-based, not
data flow. The target is read-only, so nothing was fixed and no detector was
added. Without an external anchor (C-13) the record and both SARIF files can
be rewritten together.

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
