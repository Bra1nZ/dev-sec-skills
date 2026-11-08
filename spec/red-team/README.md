# Red-Team Drills

`evals/` proves that a gate rejects a violation its author already thought of.
These drills do the opposite: they attack the committed pilot artifacts — the
craft-i18n ledger, its committed cargo log and the cell registry — and record
what happened. Eighteen attacks are blocked by the check named for them; two
pass with every gate green, and those two are the point of the exercise.

A drill is not a demo. Each one copies a real artifact into a temp directory,
applies exactly one mutation, runs the real tool, and passes only when the exit
code AND the expected message match. A crash, an unrelated error, or "exit 1
for some other reason" is a failed drill. The target repository is read, never
modified.

## Files

```text
spec/red-team/
  README.md                    # this file
  run_drills.py                # the 20 attacks, one mutation each
  2026-11-08-drills.json       # recorded result: 18 blocked, 2 allowed
```

- `make red-team` — run the drills against the current tree.
- `make red-team-record` — rewrite the recorded result.
- Not in `make verify`: the drills need the craft-i18n checkout at the recorded
  commit, and this is a point-in-time audit of gate strength, not a merge gate.

## Results, 2026-11-08 (re-measured; first run 2026-11-07)

| Drill | Attack | Result |
| --- | --- | --- |
| `escalate-tested-to-proven` | C-01 `tested` → `proven`, same run record | blocked by L4 and by `status_diff` |
| `cite-a-test-that-never-ran` | add a test ID the committed log does not contain | blocked by L2 and L3 |
| `artifact-bytes-tampered` | change `artifact_sha256` | blocked by L2 |
| `log-bytes-tampered` | change `log_sha256` | blocked by L2 |
| `counts-inflated` | claim 99/99 when the log says 26/26 | blocked by L2 |
| `remove-claim-without-tombstone` | drop C-01 from the ledger | blocked by `status_diff` |
| `tombstone-a-live-claim` | retire C-01 while it is active | blocked by L1 and `status_diff` |
| `cell-detector-artifact-missing` | point the runtime detector at a missing path | blocked by CL3 |
| `cell-runtime-without-response` | drop `violation_response` | blocked by CL1 (V2-15) |
| `stale-proof-passes-gate` | declare a proof whose record predates a change to its dependency | blocked by `--require-fresh` (V2-29) |
| `redate-the-same-run` | shift the run date one day, escalate `reviewed` → `tested` | blocked by the run-record anchor (C-41) |
| `borrow-another-claims-evidence` | give open C-08 C-01's real tests, call it `tested` | blocked by L6 (V2-34) |
| `borrow-and-declare-sharing` | borrow one test, declare it shared, still call C-08 `tested` | blocked by L6 rule 2 (V2-34) |
| `sanitizer-findings-hidden` | declare a clean ASan run over output with `ERROR: AddressSanitizer:` | blocked by L2 (V2-35) |
| `static-findings-hidden` | drop the triage entry for a real static-analysis finding (F-005) | blocked by L2 (V2-36) |
| `forge-anchored-record` | rewrite a finding's disposition after the anchor was signed | blocked by L2 anchor verification (C-41) |
| `forge-anchored-test-record` | rename the runner of a signed test run record | blocked by L2 anchor verification (C-41) |
| `drop-a-journal-entry` | delete the last verdict from the committed journal | blocked by J3 and J4 (V2-39) |
| `redate-and-resign` | re-date the run, replace `allowed_signers`, re-sign with a fresh key | **allowed** — the recorded C-13 gap |
| `rewrite-journal-and-resign` | re-date a journaled verdict, rebuild the chain, replace `allowed_signers`, re-sign the head, amend the commit | **allowed** — the recorded C-13 gap |

## The recorded silent paths

### Re-dating and re-signing

Evidence identity is `(kind, commit, artifact, command, tests, date)`. Shifting
the date makes the evidence "new", so `status_diff` accepts the escalation. On
its own the linter also accepted it while `finished_at` was compared with the
evidence date and not with anything external: the same log, one day later, and a
`reviewed` claim became `tested`.

The run-record anchor (C-41) now closes the silent version of that attack. The
signature covers `started_at` and `finished_at`, so `redate-the-same-run` fails
L2 with `anchor subject does not describe this record`; `status_diff` still
reports the escalation as legitimate, which is why the anchor check, not the
diff, is what blocks it.

What the anchor cannot stop is an actor who can also replace `allowed_signers`.
`redate-and-resign` does exactly that: it re-dates the run, generates a fresh
key, writes its public half into a replacement `allowed_signers`, signs the new
bytes with `anchor_run.py create` and points the record at them. Every gate is
green. This is the measured C-13 gap: the anchor binds a record to a key, not to
a timestamping authority, a transparency log or a revocation list.

### Rewriting the verdict journal and re-signing

The journal (V2-39) makes a verdict's past visible: a chain over every entry
plus a signed head that names the last entry, the journal hash and the exact
bytes of each covered ledger. `drop-a-journal-entry` deletes the last line of a
journal built from the real craft-i18n ledger; J3 sees that the committed file
is no longer a prefix, J1 sees `seq`/`prev` break, and J4 sees a head that
names an entry which no longer exists.

`rewrite-journal-and-resign` does what an adversary with write access to the
repository and its CI can do: re-date the first journaled verdict, recompute the
whole hash chain, point the head at the new last entry and file hash, replace
`allowed_signers` with a fresh key, sign the new head and amend the commit so
J3 compares against the rewritten history. `make journal` exits 0. The journal
binds entries to a key and to commits; it is not a transparency log, so there is
no third party who would notice that a different journal was published.

## Forging an anchored record, now blocked

`static_analysis_runs` carry an SSH-signature anchor (C-41) over the canonical
bytes of the record, including the whole triage list. `forge-anchored-record`
flips one finding from `out-of-scope` to `not-a-bug`, leaves every hash intact
and keeps the triage a bijection, so only the anchor can catch the edit. L2
recomputes the canonical bytes and reports `anchor subject does not describe
this record` before the signature check.

The gap is narrower, not gone: the key holder can re-sign any edit, and
replacing `allowed_signers` plus a new signature defeats verification entirely
(`redate-and-resign` measures it). There is no transparency log or timestamping.
Test run records and sanitizer runs now carry their own anchors
(`forge-anchored-test-record` is the negative case); proof and review records
remain unanchored.

## Borrowing, now blocked

L3 resolves a cited test ID against the suite: it proves the test exists, not
that it exercises *this* claim. In the original drill, C-08 — the open claim
about invisible Unicode Cf characters — took C-01's real tests about catalog
provenance headers, changed its status to `tested`, and every check passed.

L6 (V2-34) now closes that path with two rules. A test cited by two claims must
be declared in `shared_tests` with a reason next to each citation, and a
non-open claim must cite at least one test no other claim cites. The second
rule is what makes the declaration insufficient: the second drill borrows one
test, declares the sharing in both ledgers, and is still blocked because C-08
has no evidence of its own. In both drills `status_diff` still reports a
legitimate `open -> tested` escalation with new evidence; the block comes from
the linter.

L6 does not check that a test's assertions match the claim's wording. A test
that belongs to the claim's area but asserts something weaker still passes; the
rule detects a claim with no evidence of its own, not a mismatched assertion.

## What this does and does not show

- The 18 blocked drills show that those specific checks fire on real artifacts,
  not only on fixtures. They do not show that no other bypass exists.
- The 2 allowed drills are recorded as `allowed` in the harness. If a later gate
  starts blocking one, the drill fails and the gap entry must be updated, so this
  document cannot quietly become stale.
- The drills run `claim_lint --no-vale`: L5 prose scanning is not exercised here
  (L5 is covered by the linter evals and `make verify`).
- Only the craft-i18n ledger is attacked. It is one pilot with nine claims; the
  rbac_pg ledger is external and has no run records, so the same attack there
  would test less.
- The journal drills build a fresh journal from that ledger in a throw-away git
  repository. They exercise the gate against real claim text, not the
  repository's committed journal; J1–J4 on the committed journal run in
  `make verify` through the `journal` target.
- The attacks are static edits to committed artifacts. A compromised tool, a
  rewritten CI job, or a forged GitHub artifact are outside this scope.

## Reproduce

```bash
python3 spec/red-team/run_drills.py
python3 spec/red-team/run_drills.py --only borrow-another-claims-evidence
make red-team-record
```

Exit codes: 0 every drill matched, 1 a drill diverged, 2 the craft-i18n
checkout, the ledger, the registry, the committed log or `ssh-keygen` is
unavailable.
