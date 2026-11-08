#!/usr/bin/env python3
"""Adversarial eval runner for tools/verdict_journal.py (C-13, V2-39).

Each case builds a throw-away git repository with two claim ledgers and one
ed25519 key outside it, appends a journal, and then attacks the result:

  * a ledger status or evidence change without an append;
  * a claim retired without a `retired` entry;
  * an entry edited in place, dropped from the middle, or followed by a
    truncated history against a git ref;
  * a head whose canonical bytes were edited or whose signature comes from an
    identity outside `allowed_signers`;
  * an append over a broken chain or a broken head, which must refuse and
    leave the journal untouched.

The fixtures are synthetic. They prove the gate rejects the named defects,
not that a real journal is correct; the red-team drills exercise the committed
one.

Usage:
    python3 evals/journal/run_evals.py [--tool PATH]
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
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOOL = os.path.join(REPO, "tools", "verdict_journal.py")
DATE = "2026-11-08"
SIGNER = "journal-eval"
JOURNAL = "spec/journal/verdicts.jsonl"
HEAD = "spec/journal/head.json"


class Fail(Exception):
    pass


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_ledger(path):
    return yaml.safe_load(open(path, encoding="utf-8"))


def dump_ledger(doc, path):
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(doc, handle, sort_keys=False, allow_unicode=True)


def evidence(kind, tests=None, commit="1" * 40):
    record = {"kind": kind, "artifact": "tests/test_a.py", "commit": commit,
              "date": "2026-11-08"}
    if kind == "test":
        record.update({"tests": tests or ["t_one"],
                       "command": "python3 -m unittest -v"})
    else:
        record.pop("artifact")
        record.update({"artifact": "docs/review.md", "note": "read the code"})
    return record


def make_ledgers(repo):
    write(os.path.join(repo, "ledgers", "a.yaml"), yaml.safe_dump({
        "project": "a",
        "claims": [
            {"id": "C-01", "claim": "first", "status": "open",
             "evidence": [], "limitations": "no run yet"},
            {"id": "C-02", "claim": "second", "status": "tested",
             "evidence": [evidence("test")]},
        ],
    }, sort_keys=False, allow_unicode=True))
    write(os.path.join(repo, "ledgers", "b.yaml"), yaml.safe_dump({
        "project": "b",
        "claims": [
            {"id": "C-01", "claim": "other", "status": "reviewed",
             "evidence": [evidence("review", commit="2" * 40)]},
        ],
    }, sort_keys=False, allow_unicode=True))


def new_repo(root, name):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    make_ledgers(repo)
    for cmd in (["git", "init", "-q", "-b", "main"],
                ["git", "config", "user.email", "eval@example.invalid"],
                ["git", "config", "user.name", "journal eval"]):
        proc = run(cmd, cwd=repo)
        if proc.returncode != 0:
            raise Fail("%s failed in %s: %s" % (cmd[0], repo, proc.stderr))
    return repo


def argv(repo, allowed, sub="verify", extra=None):
    cmd = [sys.executable, TOOL, sub, "--repo", repo,
           "--journal", JOURNAL, "--head", HEAD,
           "--ledger", "ledgers/a.yaml", "--ledger", "ledgers/b.yaml",
           "--allowed-signers", allowed]
    return cmd + (extra or [])


def append(repo, key, allowed, extra=None):
    return run(argv(repo, allowed, "append",
                    ["--key", key, "--signer", SIGNER, "--date", DATE]
                    + (extra or [])))


def verify(repo, allowed, extra=None):
    return run(argv(repo, allowed, "verify", extra or []))


def expect(proc, code, needles, label):
    output = proc.stdout + proc.stderr
    if proc.returncode != code:
        raise Fail("%s: expected exit %d, got %d\n%s"
                   % (label, code, proc.returncode, output))
    for needle in needles:
        if needle not in output:
            raise Fail("%s: output does not contain %r\n%s"
                       % (label, needle, output))
    return output


def git_commit(repo, message):
    for cmd in (["git", "add", "-A"],
                ["git", "commit", "-q", "-m", message]):
        proc = run(cmd, cwd=repo)
        if proc.returncode != 0:
            raise Fail("%s failed: %s" % (" ".join(cmd), proc.stderr))


def entry_lines(repo):
    return open(os.path.join(repo, JOURNAL), encoding="utf-8").read().splitlines(True)


def write_entries(repo, lines):
    write(os.path.join(repo, JOURNAL), "".join(lines))


def case_append_and_verify(root, key, allowed):
    repo = new_repo(root, "append")
    proc = append(repo, key, allowed)
    expect(proc, 0, ["appended 3 entries", "seq 1..3"], "append")
    expect(verify(repo, allowed), 0,
           ["J1 chain         OK", "J2 ledgers       OK", "J3 history       OK",
            "J4 head anchor   OK", "total: 0 error(s), 0 warning(s), 0 info"],
           "verify")
    if len(entry_lines(repo)) != 3:
        raise Fail("append wrote %d lines, expected 3" % len(entry_lines(repo)))
    if not os.path.isfile(os.path.join(repo, HEAD + ".sig")):
        raise Fail("append did not write the head signature")


def case_idempotent_append(root, key, allowed):
    repo = new_repo(root, "idempotent")
    expect(append(repo, key, allowed), 0, ["appended 3 entries"], "first append")
    before = open(os.path.join(repo, JOURNAL), "rb").read()
    expect(append(repo, key, allowed), 0, ["no changes to append"],
           "second append")
    if open(os.path.join(repo, JOURNAL), "rb").read() != before:
        raise Fail("a no-op append rewrote the journal")


def case_status_without_entry(root, key, allowed):
    repo = new_repo(root, "status")
    append(repo, key, allowed)
    path = os.path.join(repo, "ledgers", "a.yaml")
    doc = load_ledger(path)
    doc["claims"][0]["status"] = "tested"
    doc["claims"][0].pop("limitations", None)
    doc["claims"][0]["evidence"] = [evidence("test", tests=["t_one"])]
    dump_ledger(doc, path)
    expect(verify(repo, allowed), 1,
           ["claim C-01 is 'tested' in the ledger but the journal's last word is 'open'",
            "run append"], "status change")


def case_evidence_without_entry(root, key, allowed):
    repo = new_repo(root, "evidence")
    append(repo, key, allowed)
    path = os.path.join(repo, "ledgers", "a.yaml")
    doc = load_ledger(path)
    doc["claims"][1]["evidence"][0]["date"] = "2026-11-09"
    dump_ledger(doc, path)
    expect(verify(repo, allowed), 1, ["evidence set changed"],
           "evidence change")


def case_prose_edit(root, key, allowed):
    """A limitation edit changes no verdict, but it does change the bytes the
    head attested to."""
    repo = new_repo(root, "prose")
    append(repo, key, allowed)
    path = os.path.join(repo, "ledgers", "a.yaml")
    doc = load_ledger(path)
    doc["claims"][1]["limitations"] = "still bounded; reworded only"
    dump_ledger(doc, path)
    expect(verify(repo, allowed), 1, ["the signed head names different bytes"],
           "prose edit")
    expect(append(repo, key, allowed), 0,
           ["no new verdicts; re-signing the head"], "prose re-sign")
    expect(verify(repo, allowed), 0, ["total: 0 error(s)"], "prose verify")
    if len(entry_lines(repo)) != 3:
        raise Fail("re-signing a head added a journal entry")


def case_retired_claim(root, key, allowed):
    repo = new_repo(root, "retired")
    append(repo, key, allowed)
    path = os.path.join(repo, "ledgers", "b.yaml")
    doc = load_ledger(path)
    doc["claims"] = []
    doc["retired"] = [{"id": "C-01", "reason": "moved to another repository",
                       "date": DATE}]
    dump_ledger(doc, path)
    expect(verify(repo, allowed), 1, ["needs an append with status=retired"],
           "retired claim without an entry")
    expect(append(repo, key, allowed), 0, ["appended 1 entry"], "retired append")
    expect(verify(repo, allowed), 0, ["total: 0 error(s)"], "retired verify")
    last = json.loads(entry_lines(repo)[-1])
    if last["status"] != "retired":
        raise Fail("the retired entry has status=%r" % last["status"])


def case_edited_entry(root, key, allowed):
    repo = new_repo(root, "edited")
    append(repo, key, allowed)
    lines = entry_lines(repo)
    entry = json.loads(lines[1])
    entry["status"] = "open"
    lines[1] = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
    write_entries(repo, lines)
    expect(verify(repo, allowed), 1, ["hash does not describe its bytes"],
           "edited entry")


def case_dropped_entry(root, key, allowed):
    repo = new_repo(root, "dropped")
    append(repo, key, allowed)
    lines = entry_lines(repo)
    write_entries(repo, [lines[0], lines[2]])
    expect(verify(repo, allowed), 1,
           ["the chain must be 1..N in order", "prev does not match"],
           "dropped entry")


def case_history_rewrite(root, key, allowed):
    repo = new_repo(root, "history")
    append(repo, key, allowed)
    git_commit(repo, "journal")
    path = os.path.join(repo, "ledgers", "a.yaml")
    doc = load_ledger(path)
    doc["claims"][0]["status"] = "tested"
    doc["claims"][0].pop("limitations", None)
    doc["claims"][0]["evidence"] = [evidence("test", tests=["t_one"])]
    dump_ledger(doc, path)
    expect(append(repo, key, allowed, ["--git-ref", "HEAD"]), 0,
           ["appended 1 entry"], "append after the base commit")
    git_commit(repo, "one more verdict")
    lines = entry_lines(repo)
    write_entries(repo, lines[:3])
    expect(verify(repo, allowed, ["--git-ref", "HEAD"]), 1,
           ["not append-only against HEAD"], "truncated history")


def case_head_tampered(root, key, allowed):
    """A head that is not canonical lets one JSON document have two readings
    (duplicate keys, reordering), so the gate rejects the bytes themselves."""
    repo = new_repo(root, "head")
    append(repo, key, allowed)
    path = os.path.join(repo, HEAD)
    raw = open(path, encoding="utf-8").read()
    changed = raw.replace('"generated":"%s"' % DATE,
                          '"generated":"2026-11-09"', 1)
    if changed == raw:
        raise Fail("head does not contain the generated date; cannot tamper")
    write(path, changed.replace('"generated"', '"generated" ', 1))
    expect(verify(repo, allowed), 1, ["head is not canonical JSON"],
           "edited head")


def case_head_rewritten(root, key, allowed):
    """Re-serializing the edit keeps the head canonical, so the signature is
    the only thing left to catch it."""
    repo = new_repo(root, "head-rewritten")
    append(repo, key, allowed)
    path = os.path.join(repo, HEAD)
    head = json.loads(open(path, encoding="utf-8").read())
    head["generated"] = "2026-11-09"
    write(path, json.dumps(head, sort_keys=True, separators=(",", ":")) + "\n")
    expect(verify(repo, allowed), 1, ["head signature did not verify"],
           "rewritten head")


def case_foreign_signer(root, key, allowed):
    repo = new_repo(root, "foreign")
    append(repo, key, allowed)
    foreign_key = os.path.join(root, "foreign-key")
    if run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "foreign",
            "-f", foreign_key]).returncode != 0:
        raise Fail("ssh-keygen failed for the foreign key")
    foreign = os.path.join(root, "foreign-allowed_signers")
    pub = open(foreign_key + ".pub", encoding="utf-8").read().split()
    write(foreign, "foreign %s %s\n" % (pub[0], pub[1]))
    expect(verify(repo, foreign), 1, ["head signature did not verify"],
           "foreign signer")


def case_append_refuses_broken_chain(root, key, allowed):
    repo = new_repo(root, "broken-chain")
    append(repo, key, allowed)
    lines = entry_lines(repo)
    entry = json.loads(lines[1])
    entry["status"] = "open"
    lines[1] = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
    write_entries(repo, lines)
    before = open(os.path.join(repo, JOURNAL), "rb").read()
    expect(append(repo, key, allowed), 1,
           ["refusing to append to a broken chain"], "broken chain")
    if open(os.path.join(repo, JOURNAL), "rb").read() != before:
        raise Fail("append modified a journal with a broken chain")


def case_append_refuses_tampered_head(root, key, allowed):
    repo = new_repo(root, "broken-head")
    append(repo, key, allowed)
    path = os.path.join(repo, HEAD)
    head = json.loads(open(path, encoding="utf-8").read())
    head["generated"] = "2026-11-09"
    write(path, json.dumps(head, sort_keys=True, separators=(",", ":")) + "\n")
    before = open(os.path.join(repo, JOURNAL), "rb").read()
    expect(append(repo, key, allowed), 1,
           ["refusing to append: the current head does not verify"],
           "tampered head")
    if open(os.path.join(repo, JOURNAL), "rb").read() != before:
        raise Fail("append modified the journal when the head did not verify")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=TOOL)
    args = ap.parse_args()
    tool = os.path.abspath(args.tool)
    if not os.path.isfile(tool):
        print("journal tool not found: %s" % tool, file=sys.stderr)
        return 2
    if shutil.which("ssh-keygen") is None:
        print("ssh-keygen is required for the journal eval", file=sys.stderr)
        return 2

    root = tempfile.mkdtemp(prefix="journal-eval-")
    key = os.path.join(root, "key")
    if run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", SIGNER,
            "-f", key]).returncode != 0:
        print("ssh-keygen failed to create the eval key", file=sys.stderr)
        return 2
    allowed = os.path.join(root, "allowed_signers")
    pub = open(key + ".pub", encoding="utf-8").read().split()
    write(allowed, "%s %s %s\n" % (SIGNER, pub[0], pub[1]))

    cases = [
        ("append and verify", case_append_and_verify),
        ("idempotent append", case_idempotent_append),
        ("status without an entry", case_status_without_entry),
        ("evidence without an entry", case_evidence_without_entry),
        ("prose edit and head re-sign", case_prose_edit),
        ("retired claim", case_retired_claim),
        ("edited entry", case_edited_entry),
        ("dropped entry", case_dropped_entry),
        ("truncated history", case_history_rewrite),
        ("tampered head", case_head_tampered),
        ("rewritten head", case_head_rewritten),
        ("foreign signer", case_foreign_signer),
        ("append refuses a broken chain", case_append_refuses_broken_chain),
        ("append refuses a tampered head", case_append_refuses_tampered_head),
    ]
    failed = 0
    try:
        for name, case in cases:
            try:
                case(root, key, allowed)
                print("ok   %s" % name)
            except Fail as exc:
                failed += 1
                print("FAIL %s\n     %s"
                      % (name, str(exc).replace("\n", "\n     ")))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("%d/%d journal eval cases passed" % (len(cases) - failed, len(cases)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
