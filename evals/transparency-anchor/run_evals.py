#!/usr/bin/env python3
"""Adversarial cases for tools/transparency_anchor.py and journal J5.

The provider is a deterministic local stub, so these runs do not touch Rekor,
SCITT or any network. They prove the journal binding, command adapter and J5
gate can fail on a changed journal, changed head, changed entry, missing
provider check or missing required anchor. They do not prove that a real
Rekor/SCITT service or receipt parser behaves as expected.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml  # type: ignore
except ImportError:
    print("PyYAML is required", file=sys.stderr)
    sys.exit(2)


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOOL = os.path.join(REPO, "tools", "transparency_anchor.py")
JOURNAL_TOOL = os.path.join(REPO, "tools", "verdict_journal.py")
PROVIDER = os.path.join(HERE, "provider_stub.py")
JOURNAL = os.path.join(REPO, "spec", "journal", "verdicts.jsonl")
HEAD = os.path.join(REPO, "spec", "journal", "head.json")
LEDGERS = (
    os.path.join(REPO, "spec", "pilots", "dev-sec-skills", "claims.yaml"),
    os.path.join(REPO, "spec", "pilots", "craft-i18n", "claims.yaml"),
)
ANCHORED_AT = "2026-11-17T12:00:00+00:00"


def run(argv, cwd=REPO):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)


def provider_command(pattern):
    return "python3 %s %s" % (PROVIDER, pattern)


def publish(td, journal=None, head=None, require_inclusion=False,
            out="anchor.json", anchored_at=ANCHORED_AT):
    return run([
        sys.executable, TOOL,
        "--kind", "rekor", "--provider", "offline-stub",
        "--anchored-at", anchored_at,
        "publish",
        "--journal", journal or JOURNAL,
        "--head", head or HEAD,
        "--publish-command", provider_command("{request}"),
        "--out", os.path.join(td, out),
    ] + (["--require-inclusion"] if require_inclusion else []))


def verify(td, anchor="anchor.json", journal=None, head=None, command=None,
           require_provider=False, require_inclusion=False, previous=None):
    argv = [sys.executable, TOOL,
            "--kind", "rekor",
            "verify",
            "--anchor", os.path.join(td, anchor),
            "--journal", journal or JOURNAL,
            "--head", head or HEAD]
    if command:
        argv.extend(["--verify-command", command])
    if require_provider:
        argv.append("--require-provider")
    if require_inclusion:
        argv.append("--require-inclusion")
    if previous:
        argv.extend(["--previous-anchor", os.path.join(td, previous)])
    return run(argv)


def journal_verify(anchor=None, journal=None, head=None, require=False,
                   command=None):
    argv = [sys.executable, JOURNAL_TOOL, "verify",
            "--journal", journal or JOURNAL,
            "--head", head or HEAD,
            "--ledger", LEDGERS[0], "--ledger", LEDGERS[1],
            "--allowed-signers", os.path.join(REPO, "spec", "anchor",
                                              "allowed_signers")]
    if anchor:
        argv.extend(["--transparency-anchor", anchor])
    if command:
        argv.extend(["--transparency-verify-command", command])
    if require:
        argv.append("--require-transparency")
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


def save_anchor(td, anchor, name):
    path = os.path.join(td, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(anchor, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    return path


def expect_case(name, proc, exit_code, contains=()):
    problems = []
    if proc.returncode != exit_code:
        problems.append("exit: expected %d, got %d (stderr: %s)"
                        % (exit_code, proc.returncode,
                           proc.stderr.strip()[:400]))
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
    with tempfile.TemporaryDirectory(prefix="transparency-anchor-") as td:
        proc = publish(td)
        cases.append(("publish-valid",
                      expect_case("publish-valid", proc, 0,
                                  ["transparency anchor created"])))
        if proc.returncode == 0:
            proc = verify(td)
            cases.append(("verify-local",
                          expect_case("verify-local", proc, 0,
                                      ["local anchor verified",
                                       "provider inclusion was not checked"])))
            proc = verify(td, command=provider_command("{anchor}"),
                          require_provider=True, require_inclusion=True)
            cases.append(("verify-provider",
                          expect_case("verify-provider", proc, 0,
                                      ["local and provider anchor verified"])))
        journal, head = copy_journal(td)
        with open(journal, "a", encoding="utf-8") as handle:
            handle.write("\n")
        proc = verify(td, journal=journal, head=head,
                      require_provider=True)
        cases.append(("journal-mismatch",
                      expect_case("journal-mismatch", proc, 1,
                                  ["head journal_sha256 does not match"])))
        journal, head = copy_journal(td)
        data = json.load(open(head, encoding="utf-8"))
        data["seq"] += 1
        with open(head, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        proc = verify(td, journal=journal, head=head,
                      require_provider=True)
        cases.append(("head-mismatch",
                      expect_case("head-mismatch", proc, 1,
                                  ["anchor seq does not match"])))
        anchor = load_anchor(td)
        anchor["entry_id"] = "0" * 64
        save_anchor(td, anchor, "tampered.json")
        proc = verify(td, anchor="tampered.json",
                      command=provider_command("{anchor}"),
                      require_provider=True)
        cases.append(("entry-mismatch",
                      expect_case("entry-mismatch", proc, 1,
                                  ["provider entry_id does not match"])))
        proc = verify(td, require_provider=True)
        cases.append(("provider-required",
                      expect_case("provider-required", proc, 1,
                                  ["--require-provider requires"])))
        anchor = load_anchor(td)
        anchor.pop("inclusion_proof", None)
        save_anchor(td, anchor, "no-proof.json")
        proc = verify(td, anchor="no-proof.json",
                      require_inclusion=True)
        cases.append(("inclusion-required",
                      expect_case("inclusion-required", proc, 1,
                                  ["anchor has no inclusion_proof"])))
        proc = journal_verify(anchor=os.path.join(td, "anchor.json"),
                              require=True)
        cases.append(("journal-j5-valid",
                      expect_case("journal-j5-valid", proc, 0,
                                  ["J5 external anchor OK"])))
        anchor = load_anchor(td)
        anchor["journal_head"] = "0" * 64
        tampered = save_anchor(td, anchor, "tampered-head.json")
        proc = journal_verify(anchor=tampered)
        cases.append(("journal-j5-mismatch",
                      expect_case("journal-j5-mismatch", proc, 1,
                                  ["anchor head does not match the journal head"])))
        proc = journal_verify(require=True)
        cases.append(("journal-j5-required-missing",
                      expect_case("journal-j5-required-missing", proc, 1,
                                  ["external anchor required"])))

    failed = [name for name, problems in cases if problems]
    for name, problems in cases:
        print(("FAIL %s: %s" % (name, "; ".join(problems))) if problems
              else "ok  %s" % name)
    print("%d/%d transparency-anchor eval cases passed"
          % (len(cases) - len(failed), len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
