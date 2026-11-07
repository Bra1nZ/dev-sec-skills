#!/usr/bin/env python3
"""Create and verify SSH-signature anchors for evidence records (C-13).

Three channels are anchored: `static-analysis` runs, test `run-record`s and
`sanitizer` runs. Each has its own signature namespace, so a signature made
for one channel does not verify for another.

An anchor binds a run record to bytes signed by a key that is not in the
repository. It narrows re-dating and silent rewriting: a forger who changes
the run, its triage, a hash or a timestamp must also produce a signature that
verifies against the committed `allowed_signers`. It does not stop the key
holder, or anyone who can replace `allowed_signers` and re-sign; that is the
remaining C-13 gap and the documentation says so.

    # one-time key creation; the private key stays outside the repository
    python3 tools/anchor_run.py keygen \
        --out-dir /tmp/opencode/dev-sec-skills-anchor \
        --signer dev-sec-skills-anchor-2026-11-07

    # sign run 0 of C-01 and print the YAML block to paste into the ledger
    python3 tools/anchor_run.py create \
        --ledger spec/pilots/dev-sec-skills/claims.yaml \
        --claim C-01 --run 0 \
        --key /tmp/opencode/dev-sec-skills-anchor/key \
        --signer dev-sec-skills-anchor-2026-11-07 \
        --out-dir spec/anchor \
        --allowed-signers spec/anchor/allowed_signers \
        --id ci-dev-sec-skills-prefix-2026-11-07

    # sign the first test run record of C-02
    python3 tools/anchor_run.py create \
        --ledger spec/pilots/craft-i18n/claims.yaml \
        --claim C-02 --channel run-record --run 0 \
        --key /tmp/opencode/dev-sec-skills-anchor/key \
        --signer dev-sec-skills-anchor-2026-11-07 \
        --out-dir spec/anchor --allowed-signers spec/anchor/allowed_signers \
        --id run-record-craft-i18n-c02-2026-11-07

`create` writes `<id>.json` (the canonical subject) and `<id>.json.sig`, and
prints the `anchor:` block. It does not rewrite the ledger: comments and
ordering are evidence of authorship and a YAML round-trip would destroy them.

Exit codes: 0 ok, 1 verification failed, 2 usage/tool error.
"""

import argparse
import hashlib
import os
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import anchor_subject  # noqa: E402

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_record(ledger_path, claim_id, channel, index):
    """Load one record of a channel from a claim, in ledger order.

    `static-analysis` flattens `evidence[].static_analysis_runs`;
    `run-record` flattens `evidence[].run_record` (one per evidence item);
    `sanitizer` flattens `evidence[].sanitizer_runs`.
    """
    doc = yaml.safe_load(open(ledger_path, encoding="utf-8"))
    claims = doc.get("claims") if isinstance(doc, dict) else None
    if not isinstance(claims, list):
        sys.exit("ledger has no claims list: %s" % ledger_path)
    claim = next((c for c in claims if isinstance(c, dict)
                  and c.get("id") == claim_id), None)
    if claim is None:
        sys.exit("claim %s not found in %s" % (claim_id, ledger_path))
    records = []
    for ev in claim.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        if channel == "static-analysis":
            records.extend(ev.get("static_analysis_runs") or [])
        elif channel == "run-record":
            if isinstance(ev.get("run_record"), dict):
                records.append(ev["run_record"])
        elif channel == "sanitizer":
            records.extend(ev.get("sanitizer_runs") or [])
        else:
            sys.exit("unknown channel: %s" % channel)
    if not 0 <= index < len(records):
        sys.exit("%s record %d out of range (claim %s has %d)"
                 % (channel, index, claim_id, len(records)))
    return records[index]


def keygen(args):
    os.makedirs(args.out_dir, exist_ok=True)
    key = args.key or os.path.join(args.out_dir, "key")
    if os.path.exists(key):
        sys.exit("refusing to overwrite existing key: %s" % key)
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", args.signer,
                    "-f", key], check=True)
    allowed = args.allowed_signers or os.path.join(args.out_dir, "allowed_signers")
    pub = open(key + ".pub", encoding="utf-8").read().strip()
    with open(allowed, "a", encoding="utf-8") as handle:
        handle.write("%s %s\n" % (args.signer, pub))
    print("private key: %s (do not commit)" % key)
    print("allowed_signers: %s" % allowed)
    return 0


def create(args):
    run = load_record(args.ledger, args.claim, args.channel, args.run)
    namespace = args.namespace or anchor_subject.NAMESPACES[args.channel]
    os.makedirs(args.out_dir, exist_ok=True)
    subject_path = os.path.join(args.out_dir, args.id + ".json")
    with open(subject_path, "wb") as handle:
        handle.write(anchor_subject.record_subject_bytes(args.channel, run))
    signature_path = subject_path + ".sig"
    if os.path.exists(signature_path):
        os.remove(signature_path)
    proc = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", args.key,
                           "-n", namespace, subject_path],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        return 2

    allowed = args.allowed_signers
    if allowed and not os.path.exists(allowed):
        sys.exit("allowed_signers not found: %s (run keygen first)" % allowed)
    base = os.path.abspath(args.base)
    anchor = {
        "type": "ssh-ed25519",
        "signer": args.signer,
        "namespace": namespace,
        "subject": os.path.relpath(os.path.abspath(subject_path), base),
        "subject_sha256": sha256_file(subject_path),
        "signature": os.path.relpath(os.path.abspath(signature_path), base),
        "signature_sha256": sha256_file(signature_path),
        "allowed_signers": allowed,
        "date": args.date,
    }
    print(yaml.safe_dump({"anchor": anchor}, sort_keys=False).rstrip())
    return 0


def verify(args):
    run = load_record(args.ledger, args.claim, args.channel, args.run)
    anchor = run.get("anchor")
    if not isinstance(anchor, dict):
        print("claim %s %s %d has no anchor"
              % (args.claim, args.channel, args.run), file=sys.stderr)
        return 1
    wanted = anchor_subject.NAMESPACES[args.channel]
    if anchor.get("namespace") != wanted:
        print("anchor namespace %r is not %r for channel %s"
              % (anchor.get("namespace"), wanted, args.channel), file=sys.stderr)
        return 1
    base = os.path.abspath(args.base)

    def resolve(value):
        return value if os.path.isabs(value) else os.path.join(base, value)

    subject_path = resolve(anchor.get("subject", ""))
    if not os.path.exists(subject_path):
        print("subject not found: %s" % subject_path, file=sys.stderr)
        return 1
    expected = anchor_subject.record_subject_bytes(args.channel, run)
    actual = open(subject_path, "rb").read()
    if actual != expected:
        print("subject does not match the record's canonical bytes", file=sys.stderr)
        return 1
    if sha256_file(subject_path) != anchor.get("subject_sha256"):
        print("subject_sha256 mismatch", file=sys.stderr)
        return 1
    signature_path = resolve(anchor.get("signature", ""))
    if not os.path.exists(signature_path):
        print("signature not found: %s" % signature_path, file=sys.stderr)
        return 1
    if sha256_file(signature_path) != anchor.get("signature_sha256"):
        print("signature_sha256 mismatch", file=sys.stderr)
        return 1
    allowed = resolve(anchor.get("allowed_signers", ""))
    proc = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", allowed,
         "-I", anchor.get("signer", ""), "-n", anchor.get("namespace", ""),
         "-s", signature_path],
        input=expected, capture_output=True)
    if proc.returncode != 0:
        print((proc.stdout + proc.stderr).decode("utf-8", "replace").strip(),
              file=sys.stderr)
        return 1
    print("anchor verified for %s %s %d"
          % (args.claim, args.channel, args.run))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    key = sub.add_parser("keygen", help="create an ed25519 key and allowed_signers")
    key.add_argument("--out-dir", required=True)
    key.add_argument("--signer", required=True)
    key.add_argument("--key", default=None)
    key.add_argument("--allowed-signers", default=None)
    key.set_defaults(func=keygen)

    new = sub.add_parser("create", help="sign one record and print its anchor block")
    new.add_argument("--ledger", required=True)
    new.add_argument("--claim", required=True)
    new.add_argument("--channel", default="static-analysis",
                     choices=sorted(anchor_subject.NAMESPACES))
    new.add_argument("--run", type=int, required=True,
                     help="index within the channel (default: static-analysis)")
    new.add_argument("--key", required=True)
    new.add_argument("--signer", required=True)
    new.add_argument("--namespace", default=None,
                     help="override the channel's namespace (not recommended)")
    new.add_argument("--out-dir", required=True)
    new.add_argument("--allowed-signers", default=None,
                     help="path recorded in the anchor (default: not recorded)")
    new.add_argument("--id", required=True)
    new.add_argument("--date", default=None)
    new.add_argument("--base", default=os.getcwd(),
                     help="paths in the anchor are relative to this directory")
    new.set_defaults(func=create)

    check = sub.add_parser("verify", help="verify one record's anchor")
    check.add_argument("--ledger", required=True)
    check.add_argument("--claim", required=True)
    check.add_argument("--channel", default="static-analysis",
                       choices=sorted(anchor_subject.NAMESPACES))
    check.add_argument("--run", type=int, required=True)
    check.add_argument("--base", default=os.getcwd())
    check.set_defaults(func=verify)

    args = parser.parse_args()
    if getattr(args, "date", None) is None and hasattr(args, "date"):
        from datetime import date
        args.date = date.today().isoformat()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
