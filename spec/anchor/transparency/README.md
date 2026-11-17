# Transparency log journal anchors (C-13)

This is the primary external-anchor channel. It binds one verdict-journal head
to one Rekor or SCITT entry. A transparency log gives an externally ordered,
publicly visible commitment; it still does not prove that the journal's claims
are true and does not stop an attacker who controls the repository and the
publishing pipeline from anchoring a different history later.

The adapter is provider-neutral: `tools/transparency_anchor.py` writes a
canonical request, invokes a wallet/CLI/service command, records the returned
entry, and checks the local binding later. The bundled Rekor adapter
(`tools/rekor_adapter.py`) publishes `hashedrekord` with an x509 signer, because
the public Rekor staging instance does not accept `rekord` submissions. The SSH
signature remains the repository identity; the x509 signature is an additional
transparency-log signature.

## Publish

```bash
make anchor-transparency \
  TRANSPARENCY_PUBLISH_COMMAND='python3 tools/rekor_adapter.py publish --request {request}' \
  TRANSPARENCY_ANCHORED_AT=2026-11-17T12:00:00+00:00
```

`--publish-command` is an exact command template. `{request}` is a canonical
JSON file; `{digest}` is the SHA-256 of the journal bytes. The command prints
one JSON object with at least `entry_id` and `anchored_at`, and may return:

```json
{"entry_id":"64 hex for Rekor","log_index":15,"log_id":"...","integrated_time":"...","log_root":"...","inclusion_proof":{},"signed_entry":{}}
```

The anchor never stores the command line: it may contain credentials. It does
store `provider_output_sha256`.

## Verify

```bash
make verify-transparency-anchor \
  TRANSPARENCY_VERIFY_COMMAND='python3 tools/rekor_adapter.py verify --anchor {anchor} --head {head}' \
  TRANSPARENCY_REQUIRE_PROVIDER=1 \
  TRANSPARENCY_REQUIRE_INCLUSION=1
```

Without `--verify-command`, the tool checks only the local binding. Add
`--require-provider` to fail when independent provider verification is not run.
`--require-inclusion` additionally requires an `inclusion_proof` in both the
artifact and the provider's answer.

For Rekor, `entry_id` is a 64-hex UUID. For SCITT, IDs can be provider-defined.
The provider command remains the trust boundary for parsing and verifying
provider-specific receipt bytes.

## Recorded state (2026-11-17)

One real entry exists on Rekor staging:

- entry `71d46696179fcd5dd669b111a037fb10facae7450130eda3ee7a3e3de6c224a11cad8c790f427c9f`,
  log index 56960699, integrated 2026-11-17T09:21:02Z;
- `hashedrekord` over `sha256(spec/journal/head.json)` at seq 15
  (`bd3036533b4293b7c62e915f61f310a42959c3182e47d82e5e888d4f31939a28`);
- artifact: `journal-latest.json`; the x509 signer certificate and the signed
  head bytes are committed next to it (`rekor-signer-cert.pem`,
  `journal-seq15-head.sig`), so local and provider verification are
  reproducible from the checkout alone;
- `make verify-transparency-anchor TRANSPARENCY_REQUIRE_PROVIDER=1
  TRANSPARENCY_REQUIRE_INCLUSION=1` passes against the live service.

Recorded limitations:

- The signer is a one-off self-signed certificate
  (`CN=dev-sec-skills-rekor-test`, 24-hour validity, RSA-2048). It is not a
  project identity: the entry proves that these head bytes existed and were
  signed by *somebody* holding that key at that time. The private half lives
  outside the repository (`~/.config/dev-sec-skills/anchor/rekor-rsa-key.pem`).
- The adapter compares bytes and the inclusion proof's presence; it does not
  re-derive the Merkle inclusion proof itself. A full independent verifier
  (`rekor-cli verify` or equivalent) is a separate, not-yet-built step.
- Staging is not production trust: entries there can disappear if the
  Sigstore staging instance is reset.

### Re-anchoring ritual

`TRANSPARENCY_GATE=1` makes J5 fail closed: a commit that changes journal bytes
without a matching anchor is red. Before committing a journal append:

1. run `make journal-append` (new head, re-signed);
2. publish a new entry and record the anchor:

```bash
make anchor-transparency TRANSPARENCY_ANCHORED_AT=<ISO 8601> \
  TRANSPARENCY_SIGNATURE=<path to the signature over the new head> \
  TRANSPARENCY_PUBLIC_KEY=<path to the signer certificate>
```

3. commit the new journal, head and anchor artifact in the same commit.
