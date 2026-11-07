# ASan instrumentation probe — craft-i18n, 2026-11-07

This file records one command run after the ASan test run. It is a probe, not a
new dynamic result: it checks that the binaries cargo executed actually carry
the AddressSanitizer runtime, so the clean log is not an ordinary test run with
`-Zsanitizer=address` merely present in the environment.

| Field | Value |
| --- | --- |
| Target | `/home/admini/projects/astraoffice/craft-i18n` |
| Commit | `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256` |
| Toolchain | `rustc 1.101.0-nightly (c980177d8 2026-11-06)` |
| Test binary | `/tmp/opencode/craft-i18n-asan-target/x86_64-unknown-linux-gnu/debug/build/craft-i18n-tests/24c7088f33105172/out/locales-24c7088f33105172` |
| Command | `nm <binary> \| grep -c __asan_init` |
| Result | `1` symbol |
| Binary SHA-256 | `79ac38fa8d623616bee5fd4179899a5fa5300ff9be57bcccf1a0d89fb4fd3aec` |

The binary path is under `/tmp` and is not archived; the probe is therefore a
contemporaneous observation, not a reproducible artifact. The log itself is the
evidence record; this file only documents that the recorded run was
instrumented. A forger can rewrite this file together with the log, so it does
not add an external anchor (C-13).

## Honest scope

`__asan_init` proves the runtime is linked into the executable. It does not
prove that every crate in the test was instrumented (`std` is not), that the
tests exercised the parser's memory boundaries, or that a different defect
would have been caught.
