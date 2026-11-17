#!/usr/bin/env python3
"""Deterministic offline provider used only by transparency-anchor evals."""

import hashlib
import json
import sys


ANCHORED_AT = "2026-11-17T12:00:00+00:00"


def main():
    if len(sys.argv) != 2:
        print("usage: provider_stub.py REQUEST_OR_ANCHOR.json", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        document = json.load(handle)
    digest = document["journal_sha256"]
    entry_seed = ("stub-entry:" + digest).encode("utf-8")
    root_seed = ("stub-root:" + digest).encode("utf-8")
    print(json.dumps({
        "entry_id": hashlib.sha256(entry_seed).hexdigest(),
        "log_index": 15,
        "log_id": "stub-transparency-log",
        "integrated_time": ANCHORED_AT,
        "log_root": hashlib.sha256(root_seed).hexdigest(),
        "inclusion_proof": {
            "type": "stub-inclusion",
            "value": hashlib.sha256(entry_seed + root_seed).hexdigest(),
        },
        "signed_entry": {
            "type": "stub-signed-entry",
            "value": hashlib.sha256(root_seed + entry_seed).hexdigest(),
        },
        "anchored_at": ANCHORED_AT,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
