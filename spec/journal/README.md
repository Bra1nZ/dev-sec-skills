# Verdict journal (C-13, V2-39)

`spec/journal/verdicts.jsonl` is the history of every verdict this repository
has recorded about a claim: status, evidence set and the day it was journaled,
one canonical JSON object per line, each line hashing the line before it. The
last line is named by `spec/journal/head.json`, whose bytes are signed by a key
that is not in the repository.

`tools/status_diff.py` compares two releases: it can say "this claim escalated
without new evidence". It cannot say whether a verdict existed in between, and
deleting a release tag erases the base it compared against. The journal is the
missing half: an append-only record that the gate can check against the
working tree, the committed history and a signature.

## What is journaled

The two ledgers that live in this repository:

- `spec/pilots/dev-sec-skills/claims.yaml` — the self-pilot ledger;
- `spec/pilots/craft-i18n/claims.yaml` — the second pilot.

The rbac_pg product ledger (`../rbac_pg/docs/claims.yaml`) is **not** journaled.
It lives in another checkout, and a `../` path would tie this journal to one
directory layout. That is a recorded gap, not an oversight: the journal's
coverage is exactly the ledgers it names in its signed head.

## Entry

```json
{"claim":"C-01","date":"2026-11-08","evidence":["2dd8…","5004…"],
 "hash":"ee7f…","ledger":"spec/pilots/dev-sec-skills/claims.yaml",
 "prev":"0000…0000","seq":1,"status":"tested"}
```

| field | meaning |
| --- | --- |
| `seq` | 1-based position; must equal the line number |
| `date` | the day the verdict was journaled, not the day it was first claimed |
| `ledger` | ledger path relative to the repository root |
| `claim` | claim ID |
| `status` | the ledger status at that point, or `retired` for a tombstone |
| `evidence` | sorted sha256 digests of the claim's evidence identities |
| `prev` | previous entry's `hash`, 64 zeros for the first entry |
| `hash` | sha256 of the canonical JSON of the entry without `hash` |

The evidence digest covers the same tuple `status_diff` uses for "new
evidence": `(kind, commit, artifact, command, tests, date)`. A re-dated run, a
new artifact hash or an extra test therefore needs a new entry; rewriting the
prose of a `note` does not.

## Head

`spec/journal/head.json` is canonical JSON (sorted keys, no whitespace, no
duplicate keys, one trailing newline):

```json
{"generated":"2026-11-08","head":"7cba…","journal_sha256":"998a…",
 "ledgers":[{"path":"spec/pilots/craft-i18n/claims.yaml","sha256":"e739…"},
            {"path":"spec/pilots/dev-sec-skills/claims.yaml","sha256":"ded3…"}],
 "namespace":"dev-sec-skills-verdict-journal","seq":11,
 "signer":"dev-sec-skills-anchor-2026-11-08"}
```

`head.json.sig` is a detached ed25519 signature over those exact bytes in the
`dev-sec-skills-verdict-journal` namespace. The namespace is separate from the
three evidence-anchor namespaces (`spec/anchor/README.md`), so a head signature
cannot be replayed as an anchor for a run record or a static-analysis report.

`ledgers` names the exact bytes of each ledger the head covers. That closes a
hole `status_diff` leaves open: a prose, limitation or review-note edit changes
no verdict, so J2 stays green, but it does change the bytes the signer
attested to. After such an edit `append` re-signs the head over the same chain
instead of inventing an entry.

## Checks (J1–J4)

```bash
make journal                 # J1-J4 with --git-ref HEAD
make journal-append          # append changed verdicts and re-sign the head
```

| check | what it rejects |
| --- | --- |
| **J1 chain** | a line that is not JSON, a missing/unknown field, a wrong status, a `seq` that is not 1..N, a `prev` that does not link, a `hash` that does not describe its bytes |
| **J2 ledgers** | a claim with no entry, a status or evidence set that disagrees with the ledger, a retired claim whose last entry is not `retired`, an entry for a claim that vanished without a tombstone, a journal entry naming a ledger that was not passed |
| **J3 history** | with `--git-ref`: a working journal that no longer has the committed one as a byte prefix (delete, reorder, rewrite, truncate) |
| **J4 head** | a head that is not canonical JSON, does not name the last entry or the file hash, names different ledger bytes, or whose signature does not verify against `spec/anchor/allowed_signers` |

Before the journal lands in a commit there is no base to compare against, so
the first release runs with `JOURNAL_FIRST_RELEASE=1`; J3 and J4 then report
`info` instead of an error. After that commit the flag must be `0`.

`append` is atomic: it builds the new journal and head as temporary files,
signs the temporary head, and only then replaces the originals. A signing
failure leaves the previous journal and head intact. It refuses to run when the
existing chain, head or committed prefix does not verify — so a broken state
cannot be papered over with a new entry.

The signer must be listed in `allowed_signers` with the same public key as the
private key passed to `append`; a silent key swap is refused and rotation has
to be an explicit edit.

## Threat model

| attack | caught by | residual |
| --- | --- | --- |
| edit a journaled verdict, or drop one | J1 hash/`prev`, J4 head hash | — |
| truncate or rewrite the committed journal | J3 prefix against `--git-ref` | a forger who also rewrites history |
| delete the last verdict and keep the old head | J1 + J4 | — |
| change a ledger status or evidence without an append | J2 | — |
| change ledger prose/limitations only | J4 ledger digest | re-sign re-attests the new bytes; the diff is in git |
| present a head signed by another identity | J4 `ssh-keygen -Y verify` | — |
| replace `allowed_signers` and re-sign a rewritten chain + amend the commit | **not caught** | `rewrite-journal-and-resign` drill, recorded `allowed` |
| the key holder rewrites history before signing | **not caught** | no transparency log |
| prove *when* a verdict was journaled | **not provable** | no timestamping authority |
| revoke a leaked key | **not supported** | no revocation list; rotation alone leaves old signatures valid |

The two `allowed` rows are the rest of C-13 (Rekor/SCITT, in-toto/Sigstore, a
timestamping authority, key revocation). This journal narrows silent rewriting;
it does not make the verdicts independent of whoever holds the key.

## Backfill

The first append over existing ledgers journaled each claim's current status
and evidence with the date of the append (2026-11-08), not the date the claim
was first made. That is honest but weak: the chain proves the verdict was
recorded in the journal on that date, and says nothing about earlier history.
The ledgers' own evidence dates and anchors remain the only record of when a
claim was actually established.

The backfill is 11 entries over 11 claims (2 self-pilot, 9 second-pilot) in
one `append`, followed by one signed head. Later verdicts are appended one
change at a time, so the journal grows by exactly what changed.

## Measured state (2026-11-08)

- 11 entries, seq 1..11, head `7cba4106da56`; signer
  `dev-sec-skills-anchor-2026-11-08`
  (`SHA256:cYwKmirE4uQiSRaM9qCrRnQ7mn0wjnSN4k0wRgRnyUk`).
- `make journal` → J1–J4 OK, 0 errors.
- `evals/journal/run_evals.py` → 14/14 cases (synthetic repositories).
- `spec/red-team/run_drills.py` → 20/20 drills: 18 blocked, 2 allowed by a
  recorded gap (`redate-and-resign`, `rewrite-journal-and-resign`).
- `spec/pilots/dev-sec-skills/detectors/test_verdict_journal.py` is the test
  ID `make verify` resolves to the eval.

## Limits

- The journal covers verdicts, not the records behind them. A `model-check`
  tool output or a `review` note is not anchored (C-41 covers test runs,
  static-analysis reports and sanitizer runs only), so an edit inside such a
  record changes no evidence identity and needs no entry.
- `bootstrap` does not vendor the journal: a bootstrapped target starts with
  an empty journal and its own key. The gate and the eval are vendored, the
  history is not.
- The journal's dates are local dates; two appends on one day are ordered by
  `seq`, not by time.
- The head names ledger bytes, not the repository. A ledger edit and an append
  in the same commit are indistinguishable from an append alone; the diff is
  the only record of the edit.

## Key handling

The private key lives outside the repository
(`JOURNAL_KEY ?= $(HOME)/.config/dev-sec-skills/anchor/key`). The current key
is under `/tmp/opencode/dev-sec-skills-anchor-2026-11-08/` and was created for
this increment; losing it means the head cannot be re-signed and a new identity
must be added to `allowed_signers`. Old heads keep verifying with the old
identity line, and the loss says nothing about when they were signed. That is
the same limitation as the evidence anchors, documented in
`spec/anchor/README.md`.
