#!/usr/bin/env python3
"""Deterministic offline provider used only by the blockchain-anchor evals."""

import hashlib
import json
import sys


ANCHORED_AT = "2026-11-17T12:00:00+00:00"


def main():
    if len(sys.argv) != 2:
        print("usage: provider_stub.py REQUEST.json", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        request = json.load(handle)
    digest = request["journal_sha256"]
    tx_seed = ("stub-tx:" + digest).encode("utf-8")
    block_seed = ("stub-block:" + digest).encode("utf-8")
    print(json.dumps({
        "txid": hashlib.sha256(tx_seed).hexdigest(),
        "block_height": 3123456,
        "block_hash": hashlib.sha256(block_seed).hexdigest(),
        "confirmations": 6,
        "inclusion_proof": {
            "type": "stub-merkle",
            "value": hashlib.sha256(tx_seed + block_seed).hexdigest(),
        },
        "anchored_at": ANCHORED_AT,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
