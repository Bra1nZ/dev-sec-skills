#!/usr/bin/env python3
"""Adversarial cases for tools/blockchain_anchor.py.

The provider is a deterministic local stub, so these runs do not touch any
blockchain network. They prove the binding and command adapter can fail on a
changed journal, a changed head, a changed txid, an out-of-order previous
anchor and a missing on-chain check. They do not prove that a real provider,
node or chain behaves as expected.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml  # noqa: F401 -- availability probe
except ImportError:
    print("PyYAML is required", file=sys.stderr)
    sys.exit(2)


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOOL = os.path.join(REPO, "tools", "blockchain_anchor.py")
PROVIDER = os.path.join(HERE, "provider_stub.py")
JOURNAL = os.path.join(REPO, "spec", "journal", "verdicts.jsonl")
HEAD = os.path.join(REPO, "spec", "journal", "head.json")
ANCHORED_AT = "2026-11-17T12:00:00+00:00"


def run(argv):
    return subprocess.run(argv, cwd=REPO, capture_output=True, text=True)


def provider_command():
    return "python3 %s {request}" % PROVIDER


def publish(td, journal=None, head=None, min_confirmations=1, out="anchor.json"):
    return run([
        sys.executable, TOOL,
        "--chain", "bitcoin", "--network", "testnet4",
        "--provider", "offline-stub", "--anchored-at", ANCHORED_AT,
        "--min-confirmations", str(min_confirmations),
        "publish",
        "--journal", journal or JOURNAL,
        "--head", head or HEAD,
        "--publish-command", provider_command(),
        "--out", os.path.join(td, out),
    ])


def verify(td, anchor="anchor.json", journal=None, head=None, command=None,
           require=False, previous=None, min_confirmations=1):
    argv = [sys.executable, TOOL,
            "--chain", "bitcoin", "--network", "testnet4",
            "--min-confirmations", str(min_confirmations),
            "verify",
            "--anchor", os.path.join(td, anchor),
            "--journal", journal or JOURNAL,
            "--head", head or HEAD]
    if command:
        argv.extend(["--verify-command", command])
    if require:
        argv.append("--require-onchain")
    if previous:
        argv.extend(["--previous-anchor", os.path.join(td, previous)])
    return run(argv)


def copy_journal(td):
    journal = os.path.join(td, "verdicts.jsonl")
    head = os.path.join(td, "head.json")
    shutil.copyfile(JOURNAL, journal)
    shutil.copyfile(HEAD, head)
    return journal, head


def load_anchor(td, name="anchor.json"):
    with open(os.path.join(td, name), encoding="utf-8") as handle:
        return json.load(handle)


def expect_case(name, proc, exit_code, contains=()):
    problems = []
    if proc.returncode != exit_code:
        problems.append("exit: expected %d, got %d (stderr: %s)"
                        % (exit_code, proc.returncode, proc.stderr.strip()[:400]))
    for text in contains:
        if text not in proc.stdout + proc.stderr:
            problems.append("missing output %r" % text)
    return problems


def main():
    global TOOL
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", default=TOOL)
    args = ap.parse_args()
    TOOL = args.tool
    cases = []
    with tempfile.TemporaryDirectory(prefix="blockchain-anchor-") as td:
        proc = publish(td)
        cases.append(("publish-valid",
                      expect_case("publish-valid", proc, 0,
                                  ["blockchain anchor created"])))
        if proc.returncode == 0:
            proc = verify(td)
            cases.append(("verify-local",
                          expect_case("verify-local", proc, 0,
                                      ["local anchor verified",
                                       "on-chain inclusion was not checked"])))
        journal, head = copy_journal(td)
        with open(journal, "a", encoding="utf-8") as handle:
            handle.write("\n")
        proc = verify(td, journal=journal, head=head, require=True)
        cases.append(("journal-mismatch",
                      expect_case("journal-mismatch", proc, 1,
                                  ["head journal_sha256 does not match the "
                                   "journal bytes"])))
        journal, head = copy_journal(td)
        data = json.load(open(head, encoding="utf-8"))
        data["seq"] += 1
        with open(head, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        proc = verify(td, journal=journal, head=head, require=True)
        cases.append(("head-mismatch",
                      expect_case("head-mismatch", proc, 1,
                                  ["anchor seq does not match"])))
        anchor = load_anchor(td)
        anchor["txid"] = "0" * 64
        with open(os.path.join(td, "tampered.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(anchor, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        command = "python3 %s {anchor}" % PROVIDER
        proc = verify(td, anchor="tampered.json", command=command,
                      require=True)
        cases.append(("txid-mismatch",
                      expect_case("txid-mismatch", proc, 1,
                                  ["on-chain txid does not match"])))
        anchor = load_anchor(td)
        with open(os.path.join(td, "previous.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(anchor, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        proc = verify(td, previous="previous.json")
        cases.append(("previous-order",
                      expect_case("previous-order", proc, 1,
                                  ["not later than the previous anchor"])))
        proc = verify(td, require=True)
        cases.append(("onchain-required",
                      expect_case("onchain-required", proc, 1,
                                  ["--require-onchain requires"])))
        proc = publish(td, min_confirmations=7, out="pending.json")
        cases.append(("too-few-confirmations",
                      expect_case("too-few-confirmations", proc, 1,
                                  ["only 6 confirmation(s), need 7"])))

    failed = [name for name, problems in cases if problems]
    for name, problems in cases:
        print(("FAIL %s: %s" % (name, "; ".join(problems))) if problems
              else "ok  %s" % name)
    print("%d/%d blockchain-anchor eval cases passed"
          % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
