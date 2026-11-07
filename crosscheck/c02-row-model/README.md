# c02-row-model — an independent model of the catalog row grammar

A second implementation of the craft-i18n row grammar plus a bounded
differential check against the real
`craft_i18n_tests::catalog::read_catalog`. It exists to test a claim that a
`kind: test` cannot: that the acceptance rule of the parser is what the format
document says, not only that the committed test examples pass.

The model is written from `docs/catalog-format.md` and the C-02 claim, not from
`crates/craft-i18n-tests/src/catalog.rs`. The cross-check compares accepted rows
and rejected line numbers over an enumerated space; the implementation's
message strings are not compared. See
[`spec/proofs/c02-bound-2026-11-07.md`](../../spec/proofs/c02-bound-2026-11-07.md)
for the declared bound, the space construction, the decision rule and the
limits.

## Run

The crate has a path dependency on the craft-i18n checkout, so the checkout
must exist at the path in `Cargo.toml`. The target is read, never modified.

```bash
# agreement over the bounded space
CARGO_TARGET_DIR=/tmp/opencode/c02-crosscheck-target \
  cargo run --offline --release --manifest-path crosscheck/c02-row-model/Cargo.toml

# negative control: every named model edit must be detected
CARGO_TARGET_DIR=/tmp/opencode/c02-crosscheck-target \
  cargo run --offline --release --manifest-path crosscheck/c02-row-model/Cargo.toml -- \
  --mutants

# list the model edits
... -- --list-mutants
```

Exit codes: `0` agreement (or every mutant caught), `1` a divergence (or a
surviving mutant), `2` usage error. The space size, coverage counters and
divergences are printed to stdout; a divergence prints the input with escaped
control characters, both row lists and the implementation's problem text.

The recorded runs are
[`spec/proofs/runs/c02-crosscheck-2026-11-07.json`](../../spec/proofs/runs/c02-crosscheck-2026-11-07.json)
and
[`spec/proofs/runs/c02-mutants-2026-11-07.json`](../../spec/proofs/runs/c02-mutants-2026-11-07.json),
both written by `tools/bounded_check.py`.

## Durability

`CARGO_TARGET_DIR=/tmp/opencode/c02-crosscheck-target` is a build cache, not
evidence. `/tmp` is cleared on reboot; the committed `Cargo.lock` plus the
local registry cache in `~/.cargo` are enough to rebuild offline (cold, about
38 s on the machine that recorded the runs). The recorded command embeds the
cache path but does not require the directory to exist: cargo creates it. The
evidence itself -- the two JSON records and their captured `.log` files -- is
committed under `spec/proofs/runs/` and survives a reboot.

## Files

```text
crosscheck/c02-row-model/
  Cargo.toml        # path dependency on craft-i18n-tests
  Cargo.lock        # committed so the same dependency versions resolve
  TARGET            # the pinned target commit and crate
  src/model.rs      # the independent model and the 22 named rule edits
  src/main.rs       # space generator, comparison, coverage, mutation harness
```

`Cargo.lock` is committed because a changed dependency version can change the
implementation under test without changing the target commit.
