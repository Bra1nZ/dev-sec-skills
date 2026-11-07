#!/usr/bin/env python3
"""Create and verify SSH-signature anchors for static-analysis runs (C-13).

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
        --out-dir spec/static-analysis/anchor \
        --allowed-signers spec/static-analysis/anchor/allowed_signers \
        --id ci-dev-sec-skills-prefix-2026-11-07

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

DEFAULT_NAMESPACE = "dev-sec-skills-static-analysis"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_run(ledger_path, claim_id, index):
    doc = yaml.safe_load(open(ledger_path, encoding="utf-8"))
    claims = doc.get("claims") if isinstance(doc, dict) else None
    if not isinstance(claims, list):
        sys.exit("ledger has no claims list: %s" % ledger_path)
    claim = next((c for c in claims if isinstance(c, dict)
                  and c.get("id") == claim_id), None)
    if claim is None:
        sys.exit("claim %s not found in %s" % (claim_id, ledger_path))
    runs = [run for ev in claim.get("evidence") or []
            if isinstance(ev, dict) and ev.get("static_analysis_runs")
            for run in ev["static_analysis_runs"]]
    if not 0 <= index < len(runs):
        sys.exit("run %d out of range (claim %s has %d static-analysis runs)"
                 % (index, claim_id, len(runs)))
    return runs[index]


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
    run = load_run(args.ledger, args.claim, args.run)
    os.makedirs(args.out_dir, exist_ok=True)
    subject_path = os.path.join(args.out_dir, args.id + ".json")
    with open(subject_path, "wb") as handle:
        handle.write(anchor_subject.subject_bytes(run))
    signature_path = subject_path + ".sig"
    if os.path.exists(signature_path):
        os.remove(signature_path)
    proc = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", args.key,
                           "-n", args.namespace, subject_path],
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
        "namespace": args.namespace,
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
    run = load_run(args.ledger, args.claim, args.run)
    anchor = run.get("anchor")
    if not isinstance(anchor, dict):
        print("claim %s run %d has no anchor" % (args.claim, args.run),
              file=sys.stderr)
        return 1
    base = os.path.abspath(args.base)

    def resolve(value):
        return value if os.path.isabs(value) else os.path.join(base, value)

    subject_path = resolve(anchor.get("subject", ""))
    if not os.path.exists(subject_path):
        print("subject not found: %s" % subject_path, file=sys.stderr)
        return 1
    expected = anchor_subject.subject_bytes(run)
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
    print("anchor verified for %s run %d" % (args.claim, args.run))
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

    new = sub.add_parser("create", help="sign one run and print its anchor block")
    new.add_argument("--ledger", required=True)
    new.add_argument("--claim", required=True)
    new.add_argument("--run", type=int, required=True)
    new.add_argument("--key", required=True)
    new.add_argument("--signer", required=True)
    new.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    new.add_argument("--out-dir", required=True)
    new.add_argument("--allowed-signers", default=None,
                     help="path recorded in the anchor (default: not recorded)")
    new.add_argument("--id", required=True)
    new.add_argument("--date", default=None)
    new.add_argument("--base", default=os.getcwd(),
                     help="paths in the anchor are relative to this directory")
    new.set_defaults(func=create)

    check = sub.add_parser("verify", help="verify one run's anchor")
    check.add_argument("--ledger", required=True)
    check.add_argument("--claim", required=True)
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
