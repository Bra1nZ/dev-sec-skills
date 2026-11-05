# RussianAbsolutes — Vale style package

Russian-language prose rules for the evidence-first contract: flags
unqualified absolutes ("гарантирует", "сертифицирован", "полностью
протестирован") that need a mechanism, evidence, and scope next to the claim.
Ships a vocabulary of third-party products so their legitimate certification
references are not flagged.

## Files

```
styles/
  RussianAbsolutes/
    BannedAbsolutes.yml      # substitution rule (regex stems)
  config/
    vocabularies/
      RussianAbsolutes/
        accept.txt           # third-party whitelist, calibrated on rbac_pg
```

## Usage

Standalone (Vale >= 3.x):

```
vale --config=<project>/.vale.ini <files...>
```

with a project `.vale.ini`:

```ini
StylesPath = <path-to-dev-sec-skills>/styles
MinAlertLevel = suggestion
Vocab = RussianAbsolutes

[*]
BasedOnStyles = RussianAbsolutes
```

Integrated: `tools/claim_lint.py` uses this package automatically when the
`vale` binary is available (`VALE` env var, `PATH`, or `~/.local/bin/vale`);
otherwise it falls back to its built-in line scanner. `--no-vale` forces the
fallback. The linter generates a temporary config with the project root as
the section glob, so no project files are touched.

## Cyrillic pitfalls (recorded on Vale 3.26.0)

1. **Go regex `\w` is ASCII-only.** Russian stems like `гарантиру\w*` never
   match. Use an explicit class: `гарантиру[а-яё]*`.
2. **`existence` rules do not accept `regex: true`.** Stem matching must go
   through a `substitution` rule (its `swap` keys are regex).
3. **Vocabularies live at `styles/config/vocabularies/<Name>/accept.txt`**,
   not `styles/vocab/`. An accepted phrase is exempt from the rule — this is
   how the third-party references ("сертифицированная сборка ЗСУБД") are
   suppressed.
4. **Scope control is the caller's job.** Passing a directory lints every
   supported file type; pass an explicit file list to keep `.txt` notes out.

## Pilot comparison (rbac_pg corpus, 25 markdown files, 2026-11-05)

Same word list for both engines:

| Metric | built-in L5 scanner | Vale + RussianAbsolutes |
| --- | --- | --- |
| Findings | 15 (per line) | 12 (per occurrence) |
| True self-claims | 1 borderline | 1 (same) |
| Third-party false positives | 13 ("сертифицированная сборка", "гарантирует платформа ЗСУБД") | 0 — suppressed by the vocabulary |
| Config | Python code | YAML, no code |

Known remaining gap for both engines: the *self-claim* context rule (flag an
absolute only when it is about this project) is not natively expressible in
Vale. `tools/claim_lint.py` implements it as a post-filter over Vale findings:
the nearest context marker to the match decides — a self marker ("модуль
гарантирует") keeps the warning, a third-party marker ("гарантирует платформа",
"сертифицированная ОС") downgrades it to info. Calibrated on the rbac_pg
corpus: of 12 Vale findings, 11 are third-party context (info) and one
(FSTEC-GAP.md:226 "Модуль гарантирует: ...") is a true self-claim (warning).
Negative control: synthetic self-claims stay warnings, third-party lines are
downgraded. Known limit: proximity is a line-level heuristic; a line where the
self marker is textually closer but the absolute refers to a third-party
product would be misclassified.

Two findings recorded during CI integration (2026-11-05):

1. **Silent miss with a relative root.** Vale matches sections by path; with
   `--root .` the section glob `[./**]` matched nothing and the Vale run
   returned 0 findings without an error. `claim_lint.py` now passes absolute
   paths for both the section glob and the file list.
2. **Meta false positives from the checker's own documentation.** The
   vendored `schemas/README.md` and `styles/README.md` quote the banned words
   and get flagged when the default `*.md` docs-glob scans the whole target
   repository. Resolution: do not vendor the checker's READMEs into the
   target repository (only `tools/`, `styles/` rules, `schemas/*.json`).

This package is a pilot, not a calibrated checker. Precision on this corpus
is ~8–10% without the vocabulary; treat findings as advisory, not as a
merge gate.
