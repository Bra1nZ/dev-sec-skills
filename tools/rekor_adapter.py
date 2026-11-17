#!/usr/bin/env python3
"""Publish/verify a journal head on Rekor staging via the Rekor HTTP API.

The adapter uses the existing SSH signature over the canonical head bytes. It
posts a `rekord` entry with `signature.format=ssh`; it does not create a new
key or signature. It speaks HTTP directly so a deployment does not have to
install `rekor-cli` or `cosign`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


PROVIDER = "rekor-staging"
PAYLOAD_KIND = "rekord"
API_VERSION = "0.0.1"
DEFAULT_SERVER = "https://rekor.sigstage.dev"


class AdapterError(Exception):
    """A fail-loud adapter error with a printable message."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise AdapterError("cannot read %s: %s" % (path, exc)) from exc


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise AdapterError("cannot read JSON %s: %s" % (path, exc)) from exc


def b64(data):
    return base64.b64encode(data).decode("ascii")


def iso_time(seconds):
    if not isinstance(seconds, int) or seconds < 0:
        raise AdapterError("invalid integratedTime: %r" % seconds)
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace(
        "+00:00", "Z")


def http_json(url, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = response.status
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001 - keep the original HTTP error visible
            detail = str(exc)
        raise AdapterError("Rekor %s returned %d: %s"
                           % (method, exc.code, detail)) from exc
    except OSError as exc:
        raise AdapterError("cannot reach Rekor %s: %s" % (url, exc)) from exc
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AdapterError("Rekor returned non-JSON response: %s" % exc) from exc
    return status, body, headers


def verify_ssh_signature(head_path, signature_path, public_key_path,
                         namespace, identity):
    head = read_bytes(head_path)
    signature = read_bytes(signature_path)
    public_key = read_bytes(public_key_path)
    temporary = os.path.join(os.path.dirname(os.path.abspath(head_path)),
                             ".rekor-adapter-head")
    try:
        with open(temporary, "wb") as handle:
            handle.write(head)
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", public_key_path,
             "-I", identity, "-n", namespace, "-s", signature_path],
            input=head, capture_output=True)
    except OSError as exc:
        raise AdapterError("cannot verify SSH signature: %s" % exc) from exc
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    if proc.returncode != 0:
        output = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
        raise AdapterError("SSH signature did not verify: %s" % output)
    return head, signature, public_key


def proposed_entry(head, signature, public_key, payload_kind, signature_format):
    if payload_kind == "hashedrekord":
        return {
            "kind": payload_kind,
            "apiVersion": API_VERSION,
            "spec": {
                "data": {
                    "hash": {"algorithm": "sha256",
                             "value": sha256_bytes(head)},
                },
                "signature": {
                    "content": b64(signature),
                    "publicKey": {"content": b64(public_key)},
                },
            },
        }
    return {
        "kind": payload_kind,
        "apiVersion": API_VERSION,
        "spec": {
            "data": {"content": b64(head)},
            "signature": {
                "format": "ssh",
                "content": b64(signature),
                "publicKey": {"content": b64(public_key)},
            },
        },
    }


def result_from_log_entry(entry_id, entry):
    verification = entry.get("verification") or {}
    proof = verification.get("inclusionProof")
    signed_entry = verification.get("signedEntryTimestamp")
    result = {
        "entry_id": entry_id,
        "log_index": entry.get("logIndex"),
        "log_id": entry.get("logID"),
        "integrated_time": iso_time(entry.get("integratedTime")),
        "anchored_at": iso_time(entry.get("integratedTime")),
    }
    if isinstance(proof, dict):
        result["inclusion_proof"] = proof
        if isinstance(proof.get("rootHash"), str):
            result["log_root"] = proof["rootHash"]
    if isinstance(signed_entry, str):
        result["signed_entry"] = {"value": signed_entry}
    return result


def publish(args):
    request = read_json(args.request)
    head_path = request.get("head_path")
    signature_path = request.get("signature_path") or args.signature
    public_key_path = request.get("public_key_path") or args.public_key
    server = (request.get("server") or args.server).rstrip("/")
    namespace = request.get("signature_namespace") or args.signature_namespace
    identity = request.get("signer") or args.signer
    if not head_path or not signature_path or not public_key_path:
        raise AdapterError("request must name head_path, signature_path and "
                           "public_key_path")
    payload_kind = request.get("payload_kind") or args.payload_kind
    signature_format = request.get("signature_format") or args.signature_format
    if signature_format == "ssh":
        head, signature, public_key = verify_ssh_signature(
            head_path, signature_path, public_key_path, namespace, identity)
    else:
        head = read_bytes(head_path)
        signature = read_bytes(signature_path)
        public_key = read_bytes(public_key_path)
    payload = proposed_entry(head, signature, public_key, payload_kind,
                             signature_format)
    status, response, headers = http_json(
        server + "/api/v1/log/entries", method="POST", payload=payload)
    if status not in (200, 201):
        raise AdapterError("Rekor returned unexpected status %d" % status)
    if not isinstance(response, dict) or not response:
        raise AdapterError("Rekor returned an empty log entry")
    entry_id = headers.get("ETag", "").strip().strip('"')
    if not entry_id:
        entry_id = next(iter(response))
    entry = response.get(entry_id) or next(iter(response.values()))
    if not isinstance(entry, dict):
        raise AdapterError("Rekor entry is not an object")
    result = result_from_log_entry(entry_id, entry)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def verify(args):
    anchor = read_json(args.anchor)
    entry_id = anchor.get("entry_id") or args.entry_id
    head_path = args.head
    signature_path = args.signature
    public_key_path = args.public_key
    server = args.server.rstrip("/")
    namespace = args.signature_namespace
    identity = args.signer
    payload_kind = args.payload_kind
    signature_format = args.signature_format
    if not entry_id or not head_path or not signature_path \
            or not public_key_path:
        raise AdapterError("verify needs entry_id, head, signature and "
                           "public_key")
    if signature_format == "ssh":
        head, signature, public_key = verify_ssh_signature(
            head_path, signature_path, public_key_path, namespace, identity)
    else:
        head = read_bytes(head_path)
        signature = read_bytes(signature_path)
        public_key = read_bytes(public_key_path)
    status, response, _ = http_json(
        server + "/api/v1/log/entries/" + entry_id)
    if status != 200 or not isinstance(response, dict) or not response:
        raise AdapterError("Rekor entry %s is not available" % entry_id)
    stored = response.get(entry_id) or next(iter(response.values()))
    if not isinstance(stored, dict):
        raise AdapterError("Rekor entry is not an object")
    try:
        body = json.loads(base64.b64decode(stored.get("body", "")).decode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise AdapterError("cannot parse Rekor entry body: %s" % exc) from exc
    spec = body.get("spec") if isinstance(body, dict) else None
    if body.get("kind") != payload_kind or not isinstance(spec, dict):
        raise AdapterError("Rekor entry is not a %s entry" % payload_kind)
    signature_spec = spec.get("signature") or {}
    data_spec = spec.get("data") or {}
    key_spec = signature_spec.get("publicKey") or {}
    expected = {
        "kind": payload_kind,
        "apiVersion": API_VERSION,
        "spec": proposed_entry(head, signature, public_key, payload_kind,
                               args.signature_format)["spec"],
    }
    if body != expected:
        raise AdapterError("Rekor entry bytes do not match the local head, "
                           "signature and public key")
    if base64.b64decode(signature_spec.get("content", "")) != signature:
        raise AdapterError("Rekor signature bytes do not match the local head")
    if base64.b64decode(key_spec.get("content", "")) != public_key:
        raise AdapterError("Rekor public key bytes do not match the signer")
    if payload_kind == "hashedrekord":
        if base64.b64decode(signature_spec.get("content", "")) != signature \
                or base64.b64decode(key_spec.get("content", "")) != public_key:
            raise AdapterError("Rekor signature or public key does not match "
                               "the local signer")
    else:
        if "content" not in data_spec:
            raise AdapterError("Rekor entry does not carry the head bytes")
        if base64.b64decode(data_spec["content"]) != head:
            raise AdapterError("Rekor head bytes do not match the local head")
    result = result_from_log_entry(entry_id, stored)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def parser():
    ap = argparse.ArgumentParser(
        description="Publish or verify a Rekor rekord entry for a journal head")
    sub = ap.add_subparsers(dest="command", required=True)
    new = sub.add_parser("publish", help="publish one Rekor entry")
    new.add_argument("--request", required=True)
    new.add_argument("--server", default=DEFAULT_SERVER)
    new.add_argument("--signature")
    new.add_argument("--public-key")
    new.add_argument("--signer")
    new.add_argument("--signature-namespace", default="file")
    new.add_argument("--signature-format", default="ssh")
    new.add_argument("--payload-kind", default=PAYLOAD_KIND)
    new.set_defaults(func=publish)
    check = sub.add_parser("verify", help="verify one Rekor entry")
    check.add_argument("--anchor", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--server", default=DEFAULT_SERVER)
    check.add_argument("--signature")
    check.add_argument("--public-key")
    check.add_argument("--signer")
    check.add_argument("--signature-namespace", default="file")
    check.add_argument("--signature-format", default="ssh")
    check.add_argument("--payload-kind", default=PAYLOAD_KIND)
    check.add_argument("--entry-id")
    check.set_defaults(func=verify)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except AdapterError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
