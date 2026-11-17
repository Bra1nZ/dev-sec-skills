#!/usr/bin/env python3
"""Bind a verdict-journal head to a Rekor or SCITT entry (C-13).

The tool is provider-neutral on purpose. It writes a canonical request, calls
the operator's transparency-log adapter, records the returned entry, and later
checks that the artifact still matches the exact journal and head. It does not
implement provider-specific cryptography itself; the adapter named by
`--verify-command` owns that work.

A transparency log is an external ordering and availability channel. It is not
evidence that the journal is true, and it does not stop a key holder from
rewriting the journal and publishing another entry.
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


FORMAT = "dev-sec-skills/transparency-anchor/1"
KINDS = ("rekor", "scitt")
ANCHOR_FIELDS = (
    "format", "kind", "journal_sha256", "journal_head", "journal_seq",
    "provider", "entry_id", "log_index", "log_id", "integrated_time",
    "log_root", "inclusion_proof", "signed_entry",
    "provider_output_sha256", "anchored_at",
)
RESULT_FIELDS = (
    "entry_id", "log_index", "log_id", "integrated_time", "log_root",
    "inclusion_proof", "signed_entry", "anchored_at",
)
DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
HEX_RE_80 = re.compile(r"^[0-9a-f]{80}$")


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
    if os.path.exists(path):
        raise AnchorError("anchor already exists: %s" % path)
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(obj))


def is_hex64(value):
    return isinstance(value, str) and HEX_RE.fullmatch(value) is not None


def is_hex64_or_80(value):
    return is_hex64(value) or (
        isinstance(value, str) and HEX_RE_80.fullmatch(value) is not None)


def valid_datetime(value):
    if not isinstance(value, str) or DATE_TIME_RE.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def clean_result(raw, kind, require_inclusion=False):
    if not isinstance(raw, dict):
        raise AnchorError("provider output is not a JSON object")
    unknown = sorted(set(raw) - set(RESULT_FIELDS))
    if unknown:
        raise AnchorError("provider output has unknown fields: %s"
                          % ", ".join(unknown))
    if "entry_id" not in raw:
        raise AnchorError("provider output lacks entry_id")
    entry_id = raw["entry_id"]
    if kind == "rekor" and not is_hex64_or_80(entry_id):
        raise AnchorError("invalid Rekor entry_id: %r" % entry_id)
    if kind == "scitt" and not nonempty(entry_id):
        raise AnchorError("invalid SCITT entry_id")
    result = {"entry_id": entry_id}
    if raw.get("log_index") is not None:
        index = raw["log_index"]
        if not isinstance(index, int) or index < 0:
            raise AnchorError("invalid log_index")
        result["log_index"] = index
    if raw.get("log_id") is not None:
        if not nonempty(raw["log_id"]):
            raise AnchorError("invalid log_id")
        result["log_id"] = raw["log_id"]
    if raw.get("integrated_time") is not None:
        if not valid_datetime(raw["integrated_time"]):
            raise AnchorError("integrated_time is not ISO 8601")
        result["integrated_time"] = raw["integrated_time"]
    if raw.get("log_root") is not None:
        if not nonempty(raw["log_root"]):
            raise AnchorError("invalid log_root")
        result["log_root"] = raw["log_root"]
    for field in ("inclusion_proof", "signed_entry"):
        if raw.get(field) is not None:
            if not isinstance(raw[field], dict):
                raise AnchorError("%s is not an object" % field)
            result[field] = raw[field]
    if raw.get("anchored_at") is not None:
        if not valid_datetime(raw["anchored_at"]):
            raise AnchorError("anchored_at is not ISO 8601")
        result["anchored_at"] = raw["anchored_at"]
    if require_inclusion and "inclusion_proof" not in result:
        raise AnchorError("provider output has no inclusion_proof")
    return result


def validate_anchor(anchor, require_inclusion=False):
    if not isinstance(anchor, dict):
        raise AnchorError("anchor is not a JSON object")
    if anchor.get("format") != FORMAT:
        raise AnchorError("unsupported anchor format: %r" % anchor.get("format"))
    unknown = sorted(set(anchor) - set(ANCHOR_FIELDS))
    if unknown:
        raise AnchorError("anchor has unknown fields: %s" % ", ".join(unknown))
    if anchor.get("kind") not in KINDS:
        raise AnchorError("kind must be one of: %s" % ", ".join(KINDS))
    for field in ("journal_sha256", "journal_head"):
        if not is_hex64(anchor.get(field)):
            raise AnchorError("invalid %s" % field)
    if not isinstance(anchor.get("journal_seq"), int) \
            or anchor["journal_seq"] < 1:
        raise AnchorError("invalid journal_seq")
    if not nonempty(anchor.get("provider")):
        raise AnchorError("provider must be a non-empty string")
    if not nonempty(anchor.get("entry_id")):
        raise AnchorError("entry_id must be a non-empty string")
    if anchor["kind"] == "rekor" and not is_hex64_or_80(anchor["entry_id"]):
        raise AnchorError("invalid Rekor entry_id")
    if not valid_datetime(anchor.get("anchored_at")):
        raise AnchorError("anchored_at must be ISO 8601 with an offset")
    if "provider_output_sha256" in anchor \
            and not is_hex64(anchor["provider_output_sha256"]):
        raise AnchorError("invalid provider_output_sha256")
    for field in ("inclusion_proof", "signed_entry"):
        if field in anchor and not isinstance(anchor[field], dict):
            raise AnchorError("%s is not an object" % field)
    if require_inclusion and "inclusion_proof" not in anchor:
        raise AnchorError("anchor has no inclusion_proof")


def journal_context(journal_path, head_path):
    journal_sha256 = sha256_file(journal_path)
    head = read_json(head_path)
    if not isinstance(head, dict):
        raise AnchorError("journal head is not an object")
    if head.get("journal_sha256") != journal_sha256:
        raise AnchorError("head journal_sha256 does not match the journal bytes")
    if not is_hex64(head.get("head")):
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
        "kind": args.kind,
        "journal_sha256": context["journal_sha256"],
        "journal_head": context["journal_head"],
        "journal_seq": context["journal_seq"],
        "provider": args.provider,
        "head_path": args.head,
        "journal_path": args.journal,
        "signature_path": args.signature,
        "public_key_path": args.public_key,
        "signer": args.signer,
        "signature_namespace": args.signature_namespace,
        "signature_format": args.signature_format,
        "server": args.server,
        "payload_kind": args.payload_kind,
    }
    request_file = args.request
    temporary = None
    try:
        if request_file is None:
            descriptor, request_file = tempfile.mkstemp(
                prefix="transparency-request-", suffix=".json")
            temporary = request_file
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(canonical_bytes(request))
        else:
            write_json(request_file, request)
        raw, output_sha256 = run_command_template(
            args.publish_command,
            {"digest": context["journal_sha256"], "request": request_file,
             "signature": args.signature or "",
             "public_key": args.public_key or "",
             "signer": args.signer or "",
             "server": args.server,
             "payload_kind": args.payload_kind},
            "publish",
        )
        result = clean_result(raw, args.kind, args.require_inclusion)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    anchored_at = args.anchored_at
    if result.get("anchored_at") is not None:
        if anchored_at and result["anchored_at"] != anchored_at:
            raise AnchorError("provider and --anchored-at disagree")
        anchored_at = result["anchored_at"]
    if not anchored_at:
        raise AnchorError("no anchored_at: pass --anchored-at")
    anchor = {
        "format": FORMAT,
        "kind": args.kind,
        "journal_sha256": context["journal_sha256"],
        "journal_head": context["journal_head"],
        "journal_seq": context["journal_seq"],
        "provider": args.provider,
        "entry_id": result["entry_id"],
        "provider_output_sha256": output_sha256,
        "anchored_at": anchored_at,
    }
    for field in ("log_index", "log_id", "integrated_time", "log_root",
                  "inclusion_proof", "signed_entry"):
        if field in result:
            anchor[field] = result[field]
    validate_anchor(anchor, args.require_inclusion)
    write_json(args.out, anchor)
    print("transparency anchor created: %s" % args.out)
    print("journal %s seq %d anchored as %s entry %s"
          % (anchor["journal_sha256"], anchor["journal_seq"], anchor["kind"],
             anchor["entry_id"]))
    return 0


def verify_binding(anchor_path, journal_path, head_path,
                   verify_command=None, require_provider=False,
                   require_inclusion=False, previous_anchor=None,
                   signature=None, public_key=None, signer=None,
                   signature_namespace=None, payload_kind=None,
                   signature_format=None):
    """Check a local anchor and, if requested, an independent provider answer."""
    anchor = read_json(anchor_path)
    validate_anchor(anchor, require_inclusion)
    context = journal_context(journal_path, head_path)
    if anchor["journal_sha256"] != context["journal_sha256"]:
        raise AnchorError("anchor journal digest does not match the journal")
    if anchor["journal_head"] != context["journal_head"]:
        raise AnchorError("anchor head does not match the journal head")
    if anchor["journal_seq"] != context["journal_seq"]:
        raise AnchorError("anchor seq does not match the journal head")
    if previous_anchor:
        previous = read_json(previous_anchor)
        validate_anchor(previous, require_inclusion)
        if previous["kind"] != anchor["kind"] \
                or previous["provider"] != anchor["provider"]:
            raise AnchorError("previous anchor uses a different log/provider")
        if anchor["journal_seq"] <= previous["journal_seq"]:
            raise AnchorError("current anchor is not later than the previous anchor")
        if anchor["journal_sha256"] == previous["journal_sha256"] \
                and anchor["entry_id"] == previous["entry_id"]:
            raise AnchorError("current anchor is the previous anchor")
    if require_provider and not verify_command:
        raise AnchorError("--require-provider requires --verify-command")
    if verify_command:
        raw, _ = run_command_template(
            verify_command,
            {"anchor": anchor_path, "digest": anchor["journal_sha256"],
             "journal": journal_path, "head": head_path,
             "signature": signature or "",
             "public_key": public_key or "",
             "signer": signer or "",
             "signature_namespace": signature_namespace or "",
             "payload_kind": payload_kind or "",
             "signature_format": signature_format or ""},
            "verify",
        )
        result = clean_result(raw, anchor["kind"], require_inclusion)
        if result["entry_id"] != anchor["entry_id"]:
            raise AnchorError("provider entry_id does not match the anchor")
        for field in ("log_index", "log_id", "integrated_time"):
            if field in anchor and field in result \
                    and anchor[field] != result[field]:
                raise AnchorError("provider %s does not match the anchor" % field)
        return anchor, True
    return anchor, False


def verify(args):
    anchor, provider_checked = verify_binding(
        args.anchor, args.journal, args.head, args.verify_command,
        args.require_provider, args.require_inclusion, args.previous_anchor,
        args.signature, args.public_key, args.signer,
        args.signature_namespace, args.payload_kind, args.signature_format)
    if provider_checked:
        print("local and provider anchor verified")
    else:
        print("local anchor verified; provider inclusion was not checked")
    print("journal %s seq %d head %s"
          % (anchor["journal_sha256"], anchor["journal_seq"],
             anchor["journal_head"]))
    return 0


def parser():
    ap = argparse.ArgumentParser(
        description="Publish or verify a Rekor/SCITT anchor for a journal head")
    ap.add_argument("--kind", default="rekor", choices=KINDS)
    ap.add_argument("--provider", default="public-rekor")
    ap.add_argument("--server", default="https://rekor.sigstage.dev")
    ap.add_argument("--signature", default=None)
    ap.add_argument("--public-key", default=None)
    ap.add_argument("--signer", default=None)
    ap.add_argument("--signature-namespace", default="file")
    ap.add_argument("--payload-kind", default="rekord")
    ap.add_argument("--signature-format", default="ssh")
    ap.add_argument("--anchored-at", default=None)
    sub = ap.add_subparsers(dest="command", required=True)

    new = sub.add_parser("publish", help="publish and record one anchor")
    new.add_argument("--journal", required=True)
    new.add_argument("--head", required=True)
    new.add_argument("--publish-command", required=True)
    new.add_argument("--out", required=True)
    new.add_argument("--request", default=None)
    new.add_argument("--require-inclusion", action="store_true")
    new.set_defaults(func=publish)

    check = sub.add_parser("verify", help="verify a local/provider anchor")
    check.add_argument("--anchor", required=True)
    check.add_argument("--journal", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--verify-command", default=None)
    check.add_argument("--previous-anchor", default=None)
    check.add_argument("--require-provider", action="store_true")
    check.add_argument("--require-inclusion", action="store_true")
    check.set_defaults(func=verify)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "publish" and not valid_datetime(args.anchored_at):
        print("--anchored-at must be ISO 8601 with an offset", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except AnchorError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
