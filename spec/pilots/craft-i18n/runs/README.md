# Captured run — craft-i18n test suite

`cargo-test-2026-11-07.log` is the raw stdout+stderr of one run of the target
test suite. It is the log that the stable `run_record`s in
[`../claims.yaml`](../claims.yaml) points at. The ASan evidence item for C-02
points at [`asan-test-2026-11-07.log`](asan-test-2026-11-07.log) instead, and
reuses it as its own `run_record` log.

| Field | Value |
| --- | --- |
| Target | `/home/admini/projects/astraoffice/craft-i18n` |
| Commit | `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` |
| Command | `cargo test --offline -p craft-i18n-tests` |
| Runner | `cargo test` 1.99.1, Rust 1.99 |
| Started | `2026-11-07T13:38:13+03:00` |
| Finished | `2026-11-07T13:38:32+03:00` |
| Exit code | 0 |
| Tests run | 26 (9 unit + 17 integration + 0 doc-tests) |
| Tests passed | 26 |
| `log_sha256` | `9007f42ddc8659f9e0fb8add511ff93f8098dd18512f9c2ef3926b330d84d10d` |

## What the record proves and what it does not

`claim_lint` L2 recomputes the log hash, hashes the cited source file under the
target root, checks that `finished_at` falls on the evidence date, and requires
each cited test ID to appear on a line that carries a status. That catches a
ledger re-dated without a new run, a log edited after the fact, and a citation
of a test that the run did not execute.

It does not prove the run happened. The log and the record live in the same
repository, so a forger who rewrites both consistently passes. The honest
status is: the record removes silent drift, not determined fraud. An external
anchor (Rekor/SCITT, C-13) is still an open design item.

## Reproducing

The run is deterministic in its result, not in its log bytes: timings, build
paths and the dependency fingerprint line change. A new run produces a
different hash, so all seven `log_sha256` values and the four distinct
`artifact_sha256` values in the claim ledger must be updated together with the
dates, and the change committed as new evidence.

```bash
cd /home/admini/projects/astraoffice/craft-i18n
sha256sum /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/runs/cargo-test-2026-11-07.log
cargo test --offline -p craft-i18n-tests
```

Artifact hashes at this commit:

| Artifact | SHA-256 |
| --- | --- |
| `crates/craft-i18n-tests/tests/locales.rs` | `18f6789707765aa10816a302d80b6d1d883db1c74bc5bc006fabed759aadc1a9` |
| `crates/craft-i18n-tests/src/catalog.rs` | `f62acd3be8c78ea8c47d129cbeec37d2e11458046281ea65447c3f29bb8f888f` |
| `crates/craft-i18n-tests/src/locale.rs` | `97b8bd6acb1225fecb34d8c350353ed2875e1b68b9808c68247e0a66c92cb113` |
| `crates/craft-i18n-tests/src/tree.rs` | `66c8ae9a43f553545ead55331e7f22b73cc64aeada5f20398be6894990ce0253` |

The target stays unmodified: the log is stored here, and `claim_lint` is run
with `--run-log-root` pointing at this repository.

## ASan run (V2-35)

`asan-test-2026-11-07.log` is the raw stdout+stderr of the AddressSanitizer
run cited by C-02. The same bytes serve as its `run_record` log and its
`sanitizer_runs[0].output`.

| Field | Value |
| --- | --- |
| Target | `/home/admini/projects/astraoffice/craft-i18n` |
| Commit | `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` |
| Toolchain | `rustc 1.101.0-nightly (c980177d8 2026-11-06)` |
| Instrumentation | `RUSTFLAGS=-Zsanitizer=address`; `--target x86_64-unknown-linux-gnu` keeps host proc-macro artifacts uninstrumented |
| Command | `RUSTUP_HOME=/tmp/opencode/rustup RUSTUP_TOOLCHAIN=nightly CARGO_TARGET_DIR=/tmp/opencode/craft-i18n-asan-target RUSTFLAGS=-Zsanitizer=address cargo test --offline -p craft-i18n-tests --target x86_64-unknown-linux-gnu` |
| Started | `2026-11-07T21:51:34+03:00` |
| Finished | `2026-11-07T21:53:31+03:00` |
| Exit code | 0 |
| Tests run | 26 (9 unit + 17 integration + 0 doc-tests) |
| Tests passed | 26 |
| Finding lines | 0 |
| `output_sha256` | `e90240b269aad9d6b1ba87ef92e2f2ee24700ab03d3f508683d408ff8a17fe7e` |

The nightly toolchain lives under `/tmp/opencode/rustup`, not in the user's
`~/.rustup`: `/home` was at 99 % and the stable toolchain was left untouched.
The build target directory is also under `/tmp` and is not archived.

### What the ASan record proves and what it does not

The record proves that one instrumented run of the 26-test suite ended with
exit 0 and printed no halting sanitizer line. It does not prove that the build
was instrumented: that is a separate observation, recorded in
[`asan-instrumentation-2026-11-07.md`](asan-instrumentation-2026-11-07.md),
where `nm` finds `__asan_init` and `__asan_report_load*/store*` in the executed
binary. Even that only shows the runtime is linked; `std` and the allocator are
not instrumented, the tests are a catalog-format corpus rather than a fuzz
corpus, and a different defect could still be missed. The record does not raise
C-02 above `tested`. As with the stable run, a forger can rewrite the record
and the log together; the external anchor is still C-13.

```bash
cd /home/admini/projects/astraoffice/craft-i18n
sha256sum /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log
RUSTUP_HOME=/tmp/opencode/rustup RUSTUP_TOOLCHAIN=nightly \
  CARGO_TARGET_DIR=/tmp/opencode/craft-i18n-asan-target \
  RUSTFLAGS=-Zsanitizer=address \
  cargo test --offline -p craft-i18n-tests --target x86_64-unknown-linux-gnu
```
