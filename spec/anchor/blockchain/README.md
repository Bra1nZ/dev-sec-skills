# Blockchain journal anchors (optional C-13 channel)

This channel adds an external timestamp to one verdict-journal head. It is not
a substitute for the SSH anchors or for a transparency log. A blockchain makes
the commitment public and append-only; it still does not prove that the
journal's claims are true, and an attacker who controls the repository and the
publishing pipeline can build a new history and publish a new commitment.

The workflow is intentionally provider-neutral:

```bash
python3 tools/blockchain_anchor.py publish \
  --journal spec/journal/verdicts.jsonl \
  --head spec/journal/head.json \
  --chain bitcoin --network testnet4 \
  --provider example-wallet \
  --anchored-at 2026-11-17T12:00:00+00:00 \
  --publish-command 'wallet-cli --testnet opreturn {digest}' \
  --out spec/anchor/blockchain/2026-11-17-head.json

python3 tools/blockchain_anchor.py verify \
  --anchor spec/anchor/blockchain/2026-11-17-head.json \
  --journal spec/journal/verdicts.jsonl \
  --head spec/journal/head.json
```

`--publish-command` is a command template. `{digest}` is the lowercase SHA-256
of the journal bytes and `{request}` is the path to a canonical request JSON
file. The command must print one JSON object:

```json
{"txid":"64-hex-or-0x64-hex","block_height":123,"block_hash":"...","confirmations":1}
```

The anchor stores the provider output hash, but never the command string:
a command line can contain credentials or a private-key path. `verify` always
checks the local binding. Add `--verify-command` and `--require-onchain` to
also query an independent node or service; without them the command explicitly
says that on-chain inclusion was not checked. Later anchors may be checked
against `--previous-anchor`, but replacing both local records still requires an
external observer or transparency log.
