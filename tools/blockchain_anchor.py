#!/usr/bin/env python3
"""Bind a verdict-journal head to a public blockchain transaction (C-13).

The tool is deliberately provider-neutral. It writes the canonical request
bytes, calls a wallet or node command supplied by the operator, records the
provider's answer as a canonical JSON anchor, and later checks that the anchor
still matches the exact journal and head. It never sends credentials, private
keys or the command line into the anchor artifact.

This is a timestamping commitment, not a proof that the journal is true. It
also does not stop a key holder from rewriting the journal and publishing a new
commitment. The external value is that the old and new commitments are both
public and ordered; an independent observer is still required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime


FORMAT = "dev-sec-skills/blockchain-anchor/1"
CHAINES = ("bitcoin", "ethereum")
ANCHOR_FIELDS = (
    "format", "journal_sha256", "journal_head", "journal_seq",
    "chain", "network", "txid", "block_height", "block_hash",
    "confirmations", "inclusion_proof", "provider",
    "provider_output_sha256", "anchored_at",
)
RESULT_FIELDS = ("txid", "block_height", "block_hash", "confirmations",
                 "inclusion_proof", "anchored_at")
DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class AnchorError(Exception):
    """A fail-loud error with a message safe to print."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    try:
        with open(path, "rb") as handle:
            return sha256_bytes(handle.read())
    except OSError as exc:
        raise AnchorError("cannot read %s: %s" % (path, exc)) from exc


def canonical_bytes(obj):
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        raise AnchorError("cannot read JSON %s: %s" % (path, exc)) from exc


def write_json(path, obj):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    data = canonical_bytes(obj)
    if os.path.exists(path):
        raise AnchorError("anchor already exists: %s" % path)
    with open(path, "wb") as handle:
        handle.write(data)


def is_hex(value, length):
    return isinstance(value, str) and re.fullmatch(
        r"[0-9a-f]{%d}" % length, value) is not None


def valid_txid(chain, value):
    if chain == "bitcoin":
        return is_hex(value, 64)
    return isinstance(value, str) and re.fullmatch(
        r"0x[0-9a-f]{64}", value) is not None


def valid_block_hash(chain, value):
    if chain == "bitcoin":
        return is_hex(value, 64)
    return isinstance(value, str) and re.fullmatch(
        r"0x[0-9a-f]{64}", value) is not None


def valid_datetime(value):
    if not isinstance(value, str) or DATE_TIME_RE.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def clean_result(raw, chain):
    if not isinstance(raw, dict):
        raise AnchorError("provider output is not a JSON object")
    unknown = sorted(set(raw) - set(RESULT_FIELDS))
    if unknown:
        raise AnchorError("provider output has unknown fields: %s"
                          % ", ".join(unknown))
    if "txid" not in raw or "confirmations" not in raw:
        raise AnchorError("provider output lacks txid or confirmations")
    if not valid_txid(chain, raw["txid"]):
        raise AnchorError("invalid %s txid: %r" % (chain, raw["txid"]))
    try:
        confirmations = int(raw["confirmations"])
    except (TypeError, ValueError) as exc:
        raise AnchorError("confirmations is not an integer") from exc
    if confirmations < 1:
        raise AnchorError("transaction has no confirmations")
    result = {"txid": raw["txid"], "confirmations": confirmations}
    if raw.get("block_height") is not None:
        height = raw["block_height"]
        if not isinstance(height, int) or height < 0:
            raise AnchorError("invalid block_height")
        result["block_height"] = height
    if raw.get("block_hash") is not None:
        block_hash = raw["block_hash"]
        if not valid_block_hash(chain, block_hash):
            raise AnchorError("invalid %s block hash: %r"
                              % (chain, block_hash))
        result["block_hash"] = block_hash
    if raw.get("inclusion_proof") is not None:
        if not isinstance(raw["inclusion_proof"], dict):
            raise AnchorError("inclusion_proof is not an object")
        result["inclusion_proof"] = raw["inclusion_proof"]
    if raw.get("anchored_at") is not None:
        if not valid_datetime(raw["anchored_at"]):
            raise AnchorError("provider anchored_at is not an ISO 8601 time")
        result["anchored_at"] = raw["anchored_at"]
    return result


def validate_anchor(anchor):
    if not isinstance(anchor, dict):
        raise AnchorError("anchor is not a JSON object")
    if anchor.get("format") != FORMAT:
        raise AnchorError("unsupported anchor format: %r" % anchor.get("format"))
    unknown = sorted(set(anchor) - set(ANCHOR_FIELDS))
    if unknown:
        raise AnchorError("anchor has unknown fields: %s" % ", ".join(unknown))
    for field in ("journal_sha256", "journal_head"):
        if not is_hex(anchor.get(field), 64):
            raise AnchorError("invalid %s" % field)
    if not isinstance(anchor.get("journal_seq"), int) \
            or anchor["journal_seq"] < 1:
        raise AnchorError("invalid journal_seq")
    if anchor.get("chain") not in CHAINES:
        raise AnchorError("chain must be one of: %s" % ", ".join(CHAINES))
    if not isinstance(anchor.get("network"), str) or not anchor["network"]:
        raise AnchorError("network must be a non-empty string")
    if not valid_txid(anchor["chain"], anchor.get("txid")):
        raise AnchorError("invalid %s txid"
                          % anchor["chain"])
    if not isinstance(anchor.get("confirmations"), int) \
            or anchor["confirmations"] < 1:
        raise AnchorError("invalid confirmations")
    if not isinstance(anchor.get("provider"), str) or not anchor["provider"]:
        raise AnchorError("provider must be a non-empty string")
    if not valid_datetime(anchor.get("anchored_at")):
        raise AnchorError("anchored_at must be ISO 8601 with an offset")
    if "provider_output_sha256" in anchor \
            and not is_hex(anchor["provider_output_sha256"], 64):
        raise AnchorError("invalid provider_output_sha256")
    if "inclusion_proof" in anchor \
            and not isinstance(anchor["inclusion_proof"], dict):
        raise AnchorError("inclusion_proof is not an object")


def journal_context(journal_path, head_path):
    journal_sha256 = sha256_file(journal_path)
    head = read_json(head_path)
    if not isinstance(head, dict):
        raise AnchorError("journal head is not an object")
    if head.get("journal_sha256") != journal_sha256:
        raise AnchorError("head journal_sha256 does not match the journal bytes")
    if not is_hex(head.get("head"), 64):
        raise AnchorError("journal head has no valid head hash")
    if not isinstance(head.get("seq"), int) or head["seq"] < 1:
        raise AnchorError("journal head has no valid seq")
    return {
        "journal_path": journal_path,
        "head_path": head_path,
        "journal_sha256": journal_sha256,
        "journal_head": head["head"],
        "journal_seq": head["seq"],
        "head": head,
    }


def run_command_template(template, values, description):
    if not template:
        raise AnchorError("%s command is required" % description)
    try:
        expanded = template.format(**values)
        argv = shlex.split(expanded)
    except (KeyError, ValueError) as exc:
        raise AnchorError("invalid %s command template: %s"
                          % (description, exc)) from exc
    if not argv:
        raise AnchorError("%s command is empty" % description)
    try:
        proc = subprocess.run(argv, capture_output=True)
    except OSError as exc:
        raise AnchorError("cannot start %s command: %s"
                          % (description, exc)) from exc
    if proc.returncode != 0:
        output = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
        raise AnchorError("%s command exited %d: %s"
                          % (description, proc.returncode, output))
    try:
        raw = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AnchorError("%s command did not print JSON: %s"
                          % (description, exc)) from exc
    return raw, sha256_bytes(proc.stdout)


def publish(args):
    context = journal_context(args.journal, args.head)
    request = {
        "format": FORMAT,
        "journal_sha256": context["journal_sha256"],
        "journal_head": context["journal_head"],
        "journal_seq": context["journal_seq"],
        "chain": args.chain,
        "network": args.network,
    }
    request["chain"] = args.chain
    request["network"] = args.network
    request_file = args.request
    temporary = None
    try:
        if request_file is None:
            descriptor, request_file = tempfile.mkstemp(prefix="anchor-request-",
                                                        suffix=".json")
            temporary = request_file
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(canonical_bytes(request))
        else:
            write_json(request_file, request)
        raw, output_sha256 = run_command_template(
            args.publish_command,
            {"digest": context["journal_sha256"], "request": request_file},
            "publish",
        )
        result = clean_result(raw, args.chain)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    anchored_at = args.anchored_at
    if result.get("anchored_at") and args.anchored_at \
            and result["anchored_at"] != args.anchored_at:
        raise AnchorError("provider and --anchored-at disagree")
    anchored_at = result.get("anchored_at", anchored_at)
    if not anchored_at:
        raise AnchorError("no anchored_at: pass --anchored-at")
    if result["confirmations"] < args.min_confirmations:
        raise AnchorError(
            "only %d confirmation(s), need %d"
            % (result["confirmations"], args.min_confirmations))
    anchor = {
        "format": FORMAT,
        "journal_sha256": context["journal_sha256"],
        "journal_head": context["journal_head"],
        "journal_seq": context["journal_seq"],
        "chain": args.chain,
        "network": args.network,
        "txid": result["txid"],
        "confirmations": result["confirmations"],
        "provider": args.provider,
        "provider_output_sha256": output_sha256,
        "anchored_at": anchored_at,
    }
    for field in ("block_height", "block_hash", "inclusion_proof"):
        if field in result:
            anchor[field] = result[field]
    validate_anchor(anchor)
    write_json(args.out, anchor)
    print("blockchain anchor created: %s" % args.out)
    print("journal %s anchored at %s %s txid %s with %d confirmation(s)"
          % (anchor["journal_sha256"], anchor["chain"], anchor["network"],
             anchor["txid"], anchor["confirmations"]))
    return 0


def previous_anchor(path):
    anchor = read_json(path)
    validate_anchor(anchor)
    return anchor


def verify(args):
    anchor = read_json(args.anchor)
    validate_anchor(anchor)
    context = journal_context(args.journal, args.head)
    if anchor["journal_sha256"] != context["journal_sha256"]:
        raise AnchorError("anchor journal digest does not match the journal")
    if anchor["journal_head"] != context["journal_head"]:
        raise AnchorError("anchor head does not match the journal head")
    if anchor["journal_seq"] != context["journal_seq"]:
        raise AnchorError("anchor seq does not match the journal head")
    if args.previous_anchor:
        previous = previous_anchor(args.previous_anchor)
        if previous["chain"] != anchor["chain"] \
                or previous["network"] != anchor["network"]:
            raise AnchorError("previous anchor uses a different chain/network")
        if anchor["journal_seq"] <= previous["journal_seq"]:
            raise AnchorError("current anchor is not later than the previous anchor")
        if anchor["journal_sha256"] == previous["journal_sha256"] \
                and anchor["txid"] == previous["txid"]:
            raise AnchorError("current anchor is the previous anchor")
    if args.require_onchain and not args.verify_command:
        raise AnchorError("--require-onchain requires --verify-command")
    if args.verify_command:
        raw, _ = run_command_template(
            args.verify_command,
            {"anchor": args.anchor, "digest": anchor["journal_sha256"],
             "journal": args.journal, "head": args.head},
            "verify",
        )
        result = clean_result(raw, anchor["chain"])
        if result["txid"] != anchor["txid"]:
            raise AnchorError("on-chain txid does not match the anchor")
        if result["confirmations"] < args.min_confirmations:
            raise AnchorError(
                "only %d confirmation(s), need %d"
                % (result["confirmations"], args.min_confirmations))
        for field in ("block_height", "block_hash"):
            if field in anchor and field in result \
                    and anchor[field] != result[field]:
                raise AnchorError("on-chain %s does not match the anchor" % field)
        print("local and on-chain anchor verified")
    else:
        print("local anchor verified; on-chain inclusion was not checked")
    print("journal %s seq %d head %s"
          % (anchor["journal_sha256"], anchor["journal_seq"],
             anchor["journal_head"]))
    return 0


def parser():
    ap = argparse.ArgumentParser(
        description="Publish or verify a blockchain timestamp for a journal head")
    ap.add_argument("--chain", default="bitcoin", choices=CHAINES)
    ap.add_argument("--network", default="testnet4")
    ap.add_argument("--provider", default="wallet-cli")
    ap.add_argument("--min-confirmations", type=int, default=1)
    ap.add_argument("--anchored-at", default=None)
    sub = ap.add_subparsers(dest="command", required=True)

    new = sub.add_parser("publish", help="publish and record one anchor")
    new.add_argument("--journal", required=True)
    new.add_argument("--head", required=True)
    new.add_argument("--publish-command", required=True)
    new.add_argument("--out", required=True)
    new.add_argument("--request", default=None)
    new.set_defaults(func=publish)

    check = sub.add_parser("verify", help="verify a local/on-chain anchor")
    check.add_argument("--anchor", required=True)
    check.add_argument("--journal", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--verify-command", default=None)
    check.add_argument("--previous-anchor", default=None)
    check.add_argument("--require-onchain", action="store_true")
    check.set_defaults(func=verify)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "publish" and not valid_datetime(args.anchored_at):
        print("--anchored-at must be ISO 8601 with an offset", file=sys.stderr)
        return 2
    if args.min_confirmations < 1:
        print("--min-confirmations must be at least 1", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except AnchorError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
