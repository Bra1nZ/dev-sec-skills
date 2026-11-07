# SARIF Evidence Adapters

`tools/sarif_evidence.py` (V2-23) answers a narrow question: given a SARIF 2.1.0
log from an engine, which taxonomy class does each finding belong to, and which
findings do we refuse to classify? It does not run an engine, does not judge
whether a finding is a real defect, and does not prove that a flagged site is
unprotected.

An adapter is a mapping, not a verifier. `spec/sarif/adapters.yaml` declares
three engines (Semgrep, CodeQL, Bandit), resolves each engine by
`tool.driver.name` (or `id`, or one of its `aliases` — osemgrep writes
`Semgrep OSS`), and maps every result by rule ID. Rules are ordered and the
first match wins. A finding whose engine or rule is not declared is `unmapped`
with a reason — `unknown-engine`, `unmapped-rule`, `missing-rule-id` or
`missing-location`. It is never pushed into `other` and never silently dropped.

## Files

- `adapters.yaml` — engines, ordered rule mappings, registry aliases.
- `fixtures/semgrep.sarif`, `fixtures/codeql.sarif`, `fixtures/bandit.sarif` —
  **authored** SARIF documents that follow the engines' documented shape.
- `2026-11-07-report.json` — normalized report from `make sarif-record`.
- `schemas/sarif-evidence.schema.json` — output contract.
- `tools/sarif_evidence.py` — the normalizer.
- `evals/sarif/` — 17 synthetic adversarial cases.

## Mapping: class first, cell optionally

Every rule names `taxonomy_class`, `failure_class` and `failure_mode`, which are
validated against `spec/conveyor/cell-registry.schema.json` before any input is
read. `other` is rejected in both `taxonomy_class` and `failure_mode`: the
adapters file is configuration, but it is not an escape hatch for a class the
taxonomy does not have.

`cell` is optional and uses `<registry>/<CELL-ID>` against the registries
declared in the same file. A rule may map to a class without an exact cell; the
finding then carries `cell: null`. That is deliberate. A class says "this
finding belongs to this failure family"; it does not say the rule exercises a
specific invariant, so inventing a cell would overstate the link. A rule that
does name a cell must resolve, or the run exits 2 before reading a log.

## What is proven, and what is not

The 2026-11-07 measurement over the three authored fixtures:

| Engine | Findings | Unmapped | Mapped to a cell |
| --- | --- | --- | --- |
| Semgrep | 2 | 0 | 2 |
| CodeQL | 2 | 0 | 1 |
| Bandit | 3 | 0 | 2 |

Inputs: 3, findings: 7, unmapped: 0, duplicates: 1, fixture inputs: 3,
digest `a46e207e87225a46`. The duplicate is the same Semgrep fingerprint
repeated in one log; the normalizer counts it and keeps one finding.

What this proves: the three adapters resolve engine names and rule IDs, produce
a deterministic finding per unique result, drop exact duplicates, and fail
closed on an unknown engine, an unmapped rule, a missing rule ID, a missing
location, a bad SARIF version, invalid JSON and an unknown cell. The report
digest is stable when the input order changes.

What it does not prove: that any engine produced these findings. The fixtures
are authored documents, not captured runs; every input is marked
`properties.dev-sec-skills/fixture = true` and the report records
`fixture_inputs: 3`. Nothing here shows that a real Semgrep, CodeQL or Bandit
run maps at the same rate, that the mapped rule IDs are current, or that a
finding is a true positive. Engine data flow, rule drift and false-positive
rates are out of scope.

## Fixture provenance and production use

A SARIF document that declares `properties.dev-sec-skills/fixture = true` (or
sets the same property on a run) is reported as `fixture: true`. A production
job adds `--reject-fixtures` (or `SARIF_STRICT=--reject-fixtures`) so an
authored document cannot pass as engine evidence.

```bash
# fixtures: the default local target
make sarif

# a real engine log: point the target at it and refuse fixtures
make sarif SARIF_INPUTS=artifacts/semgrep.sarif SARIF_STRICT=--reject-fixtures
```

`make sarif` is not part of `make verify`. It exercises authored fixtures, and a
green run says the mapping and the failure paths work, not that a repository is
clean. Gating a real PR needs engine output, a pinned engine version and a
recorded run.

When the scanned checkout is not the repository that holds `adapters.yaml`,
`--root` still points at this repository (the registries and the input paths are
relative to it) and `--path-root` names the checkout that absolute finding URIs
are rebased to:

```bash
python3 tools/sarif_evidence.py --config spec/sarif/adapters.yaml --root . \
  --path-root /path/to/target --max-unmapped 0 --reject-fixtures \
  spec/static-analysis/runs/ci-craft-i18n-2026-11-07.sarif
```

Without `--path-root` the finding paths stay absolute; the report is still
valid, but the bytes carry a machine-specific prefix.

## Unmapped is a result, not a crash

An unmapped finding does not abort the report; it is listed with its reason and
counted in `summary.unmapped`. `--max-unmapped N` turns the count into a gate
(default: no gate). With `--max-unmapped 0`, a new rule the adapters do not
know fails the job, which is the intended behaviour: an unknown rule must be
classified deliberately, not absorbed.

`--require-engines N` fails when fewer than N configured engines appear. It
catches the case where a job was supposed to run three analyses and only one
log was uploaded — a clean report from one engine is indistinguishable from a
clean report from three unless the count is checked.

## Add a rule mapping

1. Find the rule ID in the engine's SARIF driver rules and confirm it is the
   stable ID, not a display name.
2. Choose a `taxonomy_class` and `failure_mode` that already exist in the cell
   schema. If no class fits, that is a taxonomy change, not a new mapping.
3. Add `cell: <registry>/<CELL-ID>` only when the rule actually exercises that
   invariant; otherwise leave it out and let the finding carry `cell: null`.
4. Put narrow patterns before broad ones: the first matching rule wins, so a
   catch-all placed early shadows everything after it.
5. Run `make sarif` and `python3 evals/sarif/run_evals.py`. A new pattern that
   matches an existing rule ID silently reclassifies it; the digest changes and
   the review should explain why.
