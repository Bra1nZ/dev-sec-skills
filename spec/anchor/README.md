# Anchor directory (C-41)

Committed SSH-signature anchors for three evidence channels:

| Channel | Namespace | Signed fields |
| --- | --- | --- |
| `static-analysis` | `dev-sec-skills-static-analysis` | engine, version, command, rule hashes, target commit, both output hashes, exit code, timestamps, status, `cells`, whole triage |
| `run-record` | `dev-sec-skills-run-record` | runner, command, commit, exit code, timestamps, log and artifact hashes, test counts |
| `sanitizer` | `dev-sec-skills-sanitizer` | tool, version, build flags, command, exit code, timestamps, output hash, status |

`tools/anchor_subject.py` defines the canonical bytes per channel;
`tools/anchor_run.py` signs and verifies them with `ssh-keygen -Y sign/verify`
(ed25519). A signature made in one namespace does not verify in another, so a
static-analysis signature cannot be replayed as a test-run anchor.

## Files

- `allowed_signers` — plain text, one `signer <type> <key>` line per trusted
  identity. Committed; the private half never is.
- `<id>.json` — canonical subject, exactly the bytes that were signed.
- `<id>.json.sig` — detached signature.

The subject carries no path, so moving this directory or renaming a file does
not invalidate a signature. The ledger's `anchor.subject` and
`anchor.signature` fields are what point at the files.

## Verifying

```bash
python3 tools/anchor_run.py verify --channel static-analysis \
    --ledger spec/pilots/dev-sec-skills/claims.yaml --claim C-01 --run 0
python3 tools/anchor_run.py verify --channel run-record \
    --ledger spec/pilots/craft-i18n/claims.yaml --claim C-01 --run 0
python3 tools/anchor_run.py verify --channel sanitizer \
    --ledger spec/pilots/craft-i18n/claims.yaml --claim C-02 --run 0
```

`make verify` does the same through L2 on every anchored record; the commands
above are for checking one record without running the whole linter.

## Adding an anchor

1. Recompute the record so its hashes are current.
2. `python3 tools/anchor_run.py create --ledger ... --claim ... --channel
   <channel> --run <index> --key <path> --signer <identity> --out-dir
   spec/anchor --allowed-signers spec/anchor/allowed_signers --id <id>`
3. Paste the printed `anchor:` block into the record and commit the subject,
   the signature and the ledger together. A commit that adds the subject but
   not the signature (or the reverse) fails L1/L2.

## Key rotation

`ssh-keygen` signs with a key file, and `allowed_signers` decides which
identities verify. Rotation is therefore a change to that file, not to the
code.

- **Add a key.** Run `python3 tools/anchor_run.py keygen --out-dir <dir>
  --key <new-key> --signer <new-identity> --allowed-signers
  spec/anchor/allowed_signers`. It appends the public half. Old signatures keep
  verifying because their signer line is still present. New records may use the
  new identity immediately.
- **Retire a key that was not compromised.** Delete its line from
  `allowed_signers` and re-sign every record that named it with the new key
  (their anchors then name the new signer and the subject bytes are unchanged,
  because `signer` is not part of the subject). Removing the line alone makes
  those old anchors fail verification with an L2 error: visible, but the ledger
  stays red until every affected record is re-signed.
- **Key compromised.** Removing the line stops further verification, but it
  does not undo anything the key signed while it was live. Every record signed
  by that key has no proof it was not rewritten in that window; re-signing it
  with the new key proves only "unchanged since the re-sign", not "unchanged
  since the run". Record that in the claim's limitations rather than treating
  the re-signature as a clean bill of health.
- **Key lost.** Old records stay valid, but they cannot be edited and re-signed.
  A legitimate change (for example a re-triage) needs a new anchor, which
  requires a new key; the new key signs the record as it now stands. Again,
  that does not prove when the change happened.

## What the anchor does and does not prove

It proves that the signed bytes have not changed since the signature was made,
by an identity listed in `allowed_signers` at verification time. It does not
prove that the run happened when the record says: 10 of the 16 committed
anchors were created on 2026-11-08 over records dated 2026-11-07, so the
signature proves immutability after signing, not the run date. It also does not
stop the key holder, or anyone who can replace `allowed_signers` with their own
key and re-sign: the `redate-and-resign` red-team drill does exactly that and
every gate stays green. There is no transparency log, timestamping authority or
revocation list (C-13 remains open).

## Recorded key loss

The 2026-11-07 signer's private key lived at
`/tmp/opencode/dev-sec-skills-anchor/key` and was cleared with that directory.
Its public line stays in `allowed_signers`, so every anchor it made still
verifies. Three anchors are signed by a second identity,
`dev-sec-skills-anchor-2026-11-08`
(`SHA256:cYwKmirE4uQiSRaM9qCrRnQ7mn0wjnSN4k0wRgRnyUk`): the two
`rbac-pg-*-2026-11-08` static-analysis subjects and
`run-record-dev-sec-skills-c02-2026-11-08` (the bootstrap eval), tracked in the
same way.
The loss has two consequences: records signed by the lost key can never be
re-signed, and the new key's signature says nothing about when the record was
written.
