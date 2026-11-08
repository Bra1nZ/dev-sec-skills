#!/usr/bin/env python3
"""Append-only verdict journal with a hash chain and a signed head (C-13).

`status_diff` compares two ledgers; it cannot tell whether a verdict existed
in between, and deleting a release tag erases the base it used. This journal
is the missing history: one line per recorded verdict, each line hashing the
previous line, with the head signed by a key outside the repository.

What the chain proves: entries were not edited, reordered, inserted or
dropped without breaking the hash chain, and the head names one specific
journal byte string. What it does not prove: who wrote an entry, or when.
The key holder, or anyone who can replace `allowed_signers` and re-sign the
head, can rewrite the whole file and still pass; there is no transparency log,
timestamping authority or revocation list. That is the rest of C-13.
Backfilled entries (the first append over existing ledgers) inherit the
limitation of the ledgers they copy: the chain proves the verdict was recorded
in the journal on the entry date, not that it was first claimed then.

Entry (one canonical JSON object per line):

    seq      1-based position; must equal the line number
    date     YYYY-MM-DD, the day the verdict was journaled
    ledger   the ledger path exactly as passed to the tool
    claim    claim ID
    status   the ledger's status at that point, or "retired"
    evidence sorted sha256 digests of the claim's evidence identities
             (kind, commit, artifact, command, tests, date — the same identity
             `status_diff` uses), so any evidence edit needs a new entry
    prev     the previous entry's hash, or 64 zeros for the first
    hash     sha256 of the canonical JSON of the entry without this field

Head (`spec/journal/head.json`, canonical JSON, signed as
`head.json.sig` under the `dev-sec-skills-verdict-journal` namespace):

    seq, head, journal_sha256, generated, signer, namespace, ledgers
    (each ledger: path + sha256)

Checks:
  J1 chain      every line parses, seq is 1..N, prev links, hash recomputes
  J2 ledgers    every claim has an entry whose status and evidence set match
                the ledger; a retired claim's last entry is "retired"; an
                entry for a vanished claim needs a tombstone
  J3 history    with --git-ref, the journal at that ref is a byte prefix of
                the working file (a truncated or rewritten history is visible)
  J4 head       the head is canonical, names the last entry and the file hash,
                and its signature verifies against allowed_signers

Exit codes: 0 ok, 1 a violation, 2 usage/input/tool error.

Usage:
    python3 tools/verdict_journal.py verify \\
        --journal spec/journal/verdicts.jsonl --head spec/journal/head.json \\
        --ledger spec/pilots/dev-sec-skills/claims.yaml \\
        --ledger spec/pilots/craft-i18n/claims.yaml \\
        --allowed-signers spec/anchor/allowed_signers --git-ref HEAD

    python3 tools/verdict_journal.py append \\
        --journal spec/journal/verdicts.jsonl --head spec/journal/head.json \\
        --ledger ... --key ~/.config/dev-sec-skills/anchor/key \\
        --signer dev-sec-skills-anchor-2026-11-08 --date 2026-11-08
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import anchor_subject  # noqa: E402
import status_diff  # noqa: E402

GENESIS = "0" * 64
NAMESPACE = anchor_subject.VERDICT_JOURNAL_NAMESPACE
ENTRY_FIELDS = ("seq", "date", "ledger", "claim", "status", "evidence",
                "prev", "hash")
HEAD_FIELDS = anchor_subject.VERDICT_JOURNAL_FIELDS
ENTRY_STATUSES = {"open", "reviewed", "static-refinement", "model-checked",
                  "tested", "proven", "retired"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Finding:
    def __init__(self, check, severity, message):
        self.check = check
        self.severity = severity
        self.message = message

    def render(self):
        return "[%s] %-5s %s" % (self.check, self.severity, self.message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(obj):
    # Same bytes `anchor_subject` signs and `claim_lint` recomputes.
    return anchor_subject.canonical_bytes(obj)


def norm_path(path):
    return os.path.normpath(path).replace(os.sep, "/")


def ledger_pairs(repo, values):
    """(ledger path recorded in the journal, absolute path to read).

    The recorded path is relative to the repository, so the journal does not
    depend on where the verifier's shell started. A ledger outside the
    repository keeps a `../` path and is supported, but the journal then
    depends on that layout; the README says so.
    """
    pairs = []
    for value in values:
        absolute = os.path.abspath(value if os.path.isabs(value)
                                   else os.path.join(repo, value))
        rel = os.path.relpath(absolute, repo)
        pairs.append((norm_path(rel), absolute))
    return pairs


def entry_hash(entry):
    body = {key: value for key, value in entry.items() if key != "hash"}
    return sha256_bytes(canonical(body))


def load_journal(path):
    """Parse the file into entries; return (entries, parse errors)."""
    entries, errors = [], []
    if not os.path.exists(path):
        return entries, errors
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw and not raw.endswith(b"\n"):
        errors.append(Finding("J1", "error",
                              "journal does not end with a newline"))
    for number, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
        if not line.strip():
            errors.append(Finding("J1", "error",
                                  "line %d is blank; entries are one per line" % number))
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            errors.append(Finding("J1", "error",
                                  "line %d is not JSON: %s" % (number, exc)))
            continue
        if not isinstance(entry, dict):
            errors.append(Finding("J1", "error",
                                  "line %d is not an object" % number))
            continue
        entries.append(entry)
    return entries, errors


def check_chain(entries, findings):
    """J1: seq, prev and hash form one unbroken chain."""
    prev = GENESIS
    for index, entry in enumerate(entries, 1):
        missing = [field for field in ENTRY_FIELDS if field not in entry]
        unknown = sorted(set(entry) - set(ENTRY_FIELDS))
        if missing:
            findings.append(Finding("J1", "error",
                                    "entry %d is missing %s"
                                    % (index, ", ".join(missing))))
            continue
        if unknown:
            findings.append(Finding("J1", "error",
                                    "entry %d has unknown field(s) %s"
                                    % (index, ", ".join(unknown))))
        if not isinstance(entry["seq"], int) or entry["seq"] != index:
            findings.append(Finding("J1", "error",
                                    "entry %d has seq=%r; the chain must be 1..N in order"
                                    % (index, entry["seq"])))
        if entry["prev"] != prev:
            findings.append(Finding("J1", "error",
                                    "entry %d prev does not match the previous hash"
                                    % index))
        if not DATE_RE.match(str(entry["date"])):
            findings.append(Finding("J1", "error",
                                    "entry %d has date=%r, expected YYYY-MM-DD"
                                    % (index, entry["date"])))
        if entry["status"] not in ENTRY_STATUSES:
            findings.append(Finding("J1", "error",
                                    "entry %d has status=%r, not one of %s"
                                    % (index, entry["status"],
                                       ", ".join(sorted(ENTRY_STATUSES)))))
        if not isinstance(entry["evidence"], list):
            findings.append(Finding("J1", "error",
                                    "entry %d evidence is not a list" % index))
        if entry_hash(entry) != entry["hash"]:
            findings.append(Finding("J1", "error",
                                    "entry %d hash does not describe its bytes" % index))
        prev = entry["hash"]


def load_ledger(path):
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        raise ValueError("ledger is not an object: %s" % path)
    claims = {}
    for claim in doc.get("claims") or []:
        if isinstance(claim, dict) and claim.get("id"):
            claims[claim["id"]] = claim
    retired = set()
    for entry in doc.get("retired") or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            retired.add(entry["id"])
    return claims, retired


def evidence_digests(claim):
    """Sorted sha256 digests of the evidence identities `status_diff` uses.

    A digest, not the raw tuple, so the journal line stays small and a fine
    edit inside a `run_record` (which is not part of the identity) is still
    caught by the record's own anchor (C-41).
    """
    digests = set()
    for kind, commit, artifact, command, tests, when in status_diff.evidence_keys(claim):
        digests.add(sha256_bytes(canonical({
            "kind": kind, "commit": commit, "artifact": artifact,
            "command": command, "tests": list(tests), "date": when})))
    return sorted(digests)


def latest_by_claim(entries):
    latest = {}
    for entry in entries:
        if isinstance(entry.get("ledger"), str) and isinstance(entry.get("claim"), str):
            latest[(entry["ledger"], entry["claim"])] = entry
    return latest


def check_agreement(pairs, entries, findings):
    """J2: the journal's last word on every claim equals the current ledger."""
    latest = latest_by_claim(entries)
    verified = {path for path, _ in pairs}
    for (ledger, claim) in sorted(latest):
        if ledger not in verified:
            findings.append(Finding("J2", "error",
                                    "journal names ledger %s (claim %s), which was not "
                                    "verified; pass --ledger for it" % (ledger, claim)))
    for path, absolute in pairs:
        try:
            claims, retired = load_ledger(absolute)
        except (OSError, ValueError) as exc:
            findings.append(Finding("J2", "error",
                                    "cannot read ledger %s: %s" % (absolute, exc)))
            continue
        for cid in sorted(claims):
            claim = claims[cid]
            entry = latest.get((path, cid))
            if entry is None:
                findings.append(Finding("J2", "error",
                                        "%s: claim %s has no journal entry; run append"
                                        % (path, cid)))
                continue
            if entry["status"] != claim.get("status"):
                findings.append(Finding("J2", "error",
                                        "%s: claim %s is %r in the ledger but the journal's "
                                        "last word is %r; run append"
                                        % (path, cid, claim.get("status"), entry["status"])))
            expected = evidence_digests(claim)
            if entry["evidence"] != expected:
                findings.append(Finding("J2", "error",
                                        "%s: claim %s evidence set changed (%d in ledger, "
                                        "%d journaled); run append"
                                        % (path, cid, len(expected), len(entry["evidence"]))))
        for cid in sorted(retired):
            if cid in claims:
                findings.append(Finding("J2", "error",
                                        "%s: claim %s is both active and retired"
                                        % (path, cid)))
                continue
            entry = latest.get((path, cid))
            if entry is None:
                findings.append(Finding("J2", "error",
                                        "%s: retired claim %s has no journal entry; run append"
                                        % (path, cid)))
            elif entry["status"] != "retired":
                findings.append(Finding("J2", "error",
                                        "%s: retired claim %s is %r in the journal; a tombstone "
                                        "needs an append with status=retired"
                                        % (path, cid, entry["status"])))
        for (ledger, cid) in sorted(latest):
            if ledger != path or cid in claims or cid in retired:
                continue
            findings.append(Finding("J2", "error",
                                    "%s: journal names claim %s, which is gone and has no "
                                    "tombstone" % (path, cid)))


def git(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo,
                          capture_output=True)


def check_history(repo, journal_rel, ref, first_release, current, findings):
    """J3: the journal at REF is a byte prefix of the working file."""
    if not ref:
        return
    inside = git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        findings.append(Finding("J3", "error",
                                "--git-ref needs a git work tree: %s" % repo))
        return
    exists = git(repo, "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref)
    if exists.returncode != 0:
        findings.append(Finding("J3", "error", "base ref not found: %s" % ref))
        return
    base = git(repo, "show", "%s:%s" % (ref, journal_rel))
    if base.returncode != 0:
        if first_release:
            findings.append(Finding("J3", "info",
                                    "no journal at %s; first release, history gate skipped"
                                    % ref))
        else:
            findings.append(Finding("J3", "error",
                                    "no journal at %s:%s; set --first-release before the "
                                    "journal lands in a commit" % (ref, journal_rel)))
        return
    if not current.startswith(base.stdout):
        findings.append(Finding("J3", "error",
                                "journal is not append-only against %s: its %d bytes are no "
                                "longer a prefix of the working file"
                                % (ref, len(base.stdout))))


def head_ledger_digests(head):
    return {item.get("path"): item.get("sha256")
            for item in head.get("ledgers") or [] if isinstance(item, dict)}


def stale_ledgers(head, pairs):
    """Ledgers whose bytes differ from the ones the signed head names.

    The journal's identity for a claim is its status and evidence set, so a
    prose, limitation or review-note edit leaves J2 green. The head covers the
    exact ledger bytes, which is what makes such an edit visible without a new
    verdict: the signer attested to those bytes, not to any ledger with the
    same evidence.
    """
    listed = head_ledger_digests(head)
    stale = []
    for path, absolute in pairs:
        if listed.get(path) != sha256_file(absolute):
            stale.append(path)
    return stale


def check_head(journal, head_path, allowed_signers, first_release, findings,
               pairs=None):
    """J4: the head is canonical, describes this file and verifies.

    With `pairs`, it also checks that the head names the current bytes of each
    covered ledger. `append` passes None: it repairs a stale digest by
    re-signing, but it must still refuse a head whose chain or signature is
    broken.
    """
    entries, _ = load_journal(journal)
    if not entries:
        findings.append(Finding("J4", "error",
                                "cannot verify the head of an empty journal"))
        return
    if not os.path.exists(head_path):
        if first_release:
            findings.append(Finding("J4", "info",
                                    "no head at %s; first release, anchor gate skipped"
                                    % head_path))
        else:
            findings.append(Finding("J4", "error",
                                    "head not found: %s" % head_path))
        return
    raw = open(head_path, "rb").read()
    try:
        head = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        findings.append(Finding("J4", "error",
                                "head is not JSON: %s" % exc))
        return
    if not isinstance(head, dict):
        findings.append(Finding("J4", "error", "head is not an object"))
        return
    missing = [field for field in HEAD_FIELDS if field not in head]
    if missing:
        findings.append(Finding("J4", "error",
                                "head is missing %s" % ", ".join(missing)))
        return
    if head.get("namespace") != NAMESPACE:
        findings.append(Finding("J4", "error",
                                "head namespace %r is not %r"
                                % (head.get("namespace"), NAMESPACE)))
    if not DATE_RE.match(str(head.get("generated"))):
        findings.append(Finding("J4", "error",
                                "head generated=%r, expected YYYY-MM-DD"
                                % head.get("generated")))
    last = entries[-1]
    if head.get("seq") != last.get("seq"):
        findings.append(Finding("J4", "error",
                                "head seq=%r does not name the last entry (%r)"
                                % (head.get("seq"), last.get("seq"))))
    if head.get("head") != last.get("hash"):
        findings.append(Finding("J4", "error",
                                "head hash does not describe the last entry"))
    journal_digest = sha256_file(journal)
    if head.get("journal_sha256") != journal_digest:
        findings.append(Finding("J4", "error",
                                "head journal_sha256 does not describe this file"))
    expected = {key: head.get(key) for key in
                anchor_subject.VERDICT_JOURNAL_FIELDS if key != "ledgers"}
    expected["ledgers"] = [
        {"path": item.get("path"), "sha256": item.get("sha256")}
        for item in head.get("ledgers") or [] if isinstance(item, dict)]
    if canonical(expected) != raw:
        findings.append(Finding("J4", "error",
                                "head is not canonical JSON: the signed bytes must be exactly "
                                "the canonical form (sorted keys, no extra whitespace, no "
                                "duplicate keys)"))
        return
    if pairs is not None:
        for path in stale_ledgers(head, pairs):
            findings.append(Finding("J4", "error",
                                    "%s: the signed head names different bytes for this "
                                    "ledger (a prose or limitation edit, not a verdict); "
                                    "run append to re-sign the head" % path))
    signature = head_path + ".sig"
    if not os.path.exists(signature):
        findings.append(Finding("J4", "error",
                                "head signature not found: %s" % signature))
        return
    proc = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
         "-I", head.get("signer", ""), "-n", head.get("namespace", ""),
         "-s", signature],
        input=raw, capture_output=True)
    if proc.returncode != 0:
        findings.append(Finding("J4", "error",
                                "head signature did not verify against %s: %s"
                                % (allowed_signers,
                                   (proc.stdout + proc.stderr).decode(
                                       "utf-8", "replace").strip())))


def report(label, sections, findings):
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]
    for name, label_text in sections:
        rows = [f for f in findings if f.check == name]
        if not rows:
            print("  %s %-13s OK" % (name, label_text))
            continue
        print("  %s %-13s %d error(s), %d warning(s), %d info"
              % (name, label_text,
                 sum(1 for f in rows if f.severity == "error"),
                 sum(1 for f in rows if f.severity == "warning"),
                 sum(1 for f in rows if f.severity == "info")))
        for finding in rows:
            print("      %s" % finding.render())
    print("total: %d error(s), %d warning(s), %d info"
          % (len(errors), len(warnings), len(infos)))
    return 1 if errors else 0


def verify(args):
    label = norm_path(os.path.relpath(args.journal, args.repo))
    if not os.path.isfile(args.journal):
        print("journal not found: %s" % args.journal, file=sys.stderr)
        return 2
    entries, findings = load_journal(args.journal)
    print("journal: %s | entries: %d" % (label, len(entries)))
    check_chain(entries, findings)
    pairs = ledger_pairs(args.repo, args.ledger)
    check_agreement(pairs, entries, findings)
    check_history(args.repo, norm_path(os.path.relpath(args.journal, args.repo)),
                  args.git_ref, args.first_release,
                  open(args.journal, "rb").read(), findings)
    check_head(args.journal, args.head, args.allowed_signers,
               args.first_release, findings, pairs)
    return report(label, (("J1", "chain"), ("J2", "ledgers"),
                          ("J3", "history"), ("J4", "head anchor")), findings)


def signer_key_matches(allowed_signers, signer, key):
    """The private key's public half must be the line listed for `signer`."""
    if not os.path.exists(key + ".pub"):
        raise SystemExit("public key not found: %s.pub" % key)
    if not os.path.isfile(allowed_signers):
        raise SystemExit("allowed_signers not found: %s" % allowed_signers)
    public = open(key + ".pub", encoding="utf-8").read().split()
    # key.pub is "type base64 [comment]"; allowed_signers is
    # "principal type base64 [options]".
    canonical_key = tuple(public[0:2]) if len(public) >= 2 else ()
    for line in open(allowed_signers, encoding="utf-8"):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == signer:
            listed = tuple(parts[1:3])
            if listed != canonical_key:
                raise SystemExit(
                    "signer %r is listed with a different key in %s; rotate it explicitly"
                    % (signer, allowed_signers))
            return
    raise SystemExit("signer %r is not listed in %s" % (signer, allowed_signers))


def append(args):
    entries, findings = load_journal(args.journal)
    check_chain(entries, findings)
    if any(f.severity == "error" for f in findings):
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        print("refusing to append to a broken chain", file=sys.stderr)
        return 1
    if os.path.exists(args.head):
        head_findings = []
        check_head(args.journal, args.head, args.allowed_signers, False,
                   head_findings)
        if any(f.severity == "error" for f in head_findings):
            for finding in head_findings:
                print(finding.render(), file=sys.stderr)
            print("refusing to append: the current head does not verify",
                  file=sys.stderr)
            return 1
    current = open(args.journal, "rb").read() if os.path.exists(args.journal) else b""
    history_findings = []
    check_history(args.repo, norm_path(os.path.relpath(args.journal, args.repo)),
                  args.git_ref, args.first_release, current, history_findings)
    if any(f.severity == "error" for f in history_findings):
        for finding in history_findings:
            print(finding.render(), file=sys.stderr)
        print("refusing to append: history does not verify", file=sys.stderr)
        return 1

    latest = latest_by_claim(entries)
    pairs = ledger_pairs(args.repo, args.ledger)
    changes = []
    for path, absolute in pairs:
        try:
            claims, retired = load_ledger(absolute)
        except (OSError, ValueError) as exc:
            print("cannot read ledger %s: %s" % (absolute, exc), file=sys.stderr)
            return 2
        for cid in sorted(claims):
            claim = claims[cid]
            entry = latest.get((path, cid))
            state = {"status": claim.get("status"),
                     "evidence": evidence_digests(claim)}
            if entry is None or entry["status"] != state["status"] \
                    or entry["evidence"] != state["evidence"]:
                changes.append({"ledger": path, "claim": cid, **state})
        for cid in sorted(retired - set(claims)):
            entry = latest.get((path, cid))
            if entry is None or entry["status"] != "retired":
                changes.append({"ledger": path, "claim": cid,
                                "status": "retired", "evidence": []})

    if not changes:
        # A prose or limitation edit changes the ledger bytes the head attests
        # but adds no verdict. Re-sign the same chain instead of inventing an
        # entry, so J4 keeps naming the current ledger bytes.
        fresh = True
        if os.path.exists(args.head):
            try:
                head_doc = json.loads(open(args.head, "rb").read().decode("utf-8"))
            except ValueError:
                print("refusing to append: the head is not JSON", file=sys.stderr)
                return 1
            fresh = not stale_ledgers(head_doc, pairs)
        if fresh:
            print("journal: no changes to append (%d entries)" % len(entries))
            return 0
        print("journal: no new verdicts; re-signing the head over the current "
              "ledger bytes")

    signer_key_matches(args.allowed_signers, args.signer, args.key)
    journal_dir = os.path.dirname(args.journal) or "."
    head_dir = os.path.dirname(args.head) or "."
    os.makedirs(journal_dir, exist_ok=True)
    os.makedirs(head_dir, exist_ok=True)
    prev = entries[-1]["hash"] if entries else GENESIS
    seq = len(entries)
    lines = []
    re_signed_only = not changes
    for change in changes:
        seq += 1
        entry = {"seq": seq, "date": args.date, "ledger": change["ledger"],
                 "claim": change["claim"], "status": change["status"],
                 "evidence": change["evidence"], "prev": prev}
        entry["hash"] = entry_hash(entry)
        prev = entry["hash"]
        lines.append(entry)

    # Build the new journal and its head in temporary files, sign the temporary
    # head, and only then replace the originals. A signing failure must not
    # leave appended lines with a stale signature: that state fails J4 and the
    # next append would refuse to run.
    journal_tmp = args.journal + ".tmp"
    head_tmp = args.head + ".tmp"
    signature_tmp = head_tmp + ".sig"
    signature = args.head + ".sig"
    previous = open(args.journal, "rb").read() if os.path.exists(args.journal) else b""
    with open(journal_tmp, "wb") as target:
        target.write(previous)
    with open(journal_tmp, "ab") as handle:
        for entry in lines:
            handle.write(json.dumps(entry, sort_keys=True,
                                    separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")
    head = {
        "seq": seq,
        "head": prev,
        "journal_sha256": sha256_file(journal_tmp),
        "generated": args.date,
        "signer": args.signer,
        "namespace": NAMESPACE,
        "ledgers": sorted(
            ({"path": path, "sha256": sha256_file(absolute)}
             for path, absolute in pairs), key=lambda item: item["path"]),
    }
    with open(head_tmp, "wb") as handle:
        handle.write(anchor_subject.verdict_journal_subject_bytes(head))
    if os.path.exists(signature_tmp):
        os.remove(signature_tmp)
    proc = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", args.key,
                           "-n", NAMESPACE, head_tmp],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        for path in (journal_tmp, head_tmp, signature_tmp):
            if os.path.exists(path):
                os.remove(path)
        print(proc.stdout + proc.stderr, file=sys.stderr)
        return 2
    os.replace(journal_tmp, args.journal)
    os.replace(head_tmp, args.head)
    os.replace(signature_tmp, signature)
    if re_signed_only:
        print("journal: 0 new entries | seq 1..%d | head %s" % (seq, prev[:12]))
    else:
        print("journal: appended %d entr%s | seq %d..%d | head %s"
              % (len(lines), "y" if len(lines) == 1 else "ies",
                 seq - len(lines) + 1, seq, prev[:12]))
    print("head: %s (and %s)" % (args.head, os.path.basename(signature)))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    def common(parser):
        parser.add_argument("--repo", default=os.getcwd(),
                            help="repository root (default: the working directory)")
        parser.add_argument("--journal", default="spec/journal/verdicts.jsonl")
        parser.add_argument("--head", default="spec/journal/head.json")
        parser.add_argument("--ledger", action="append", required=True,
                            help="claim ledger to cover; repeat for each ledger")
        parser.add_argument("--allowed-signers",
                            default="spec/anchor/allowed_signers")
        parser.add_argument("--git-ref", default=None,
                            help="base ref the journal must extend (prefix check)")
        parser.add_argument("--first-release", action="store_true",
                            help="allow a missing journal or head at the base ref")

    check = sub.add_parser("verify", help="verify the chain, ledgers, history and head")
    common(check)
    check.set_defaults(func=verify)

    add = sub.add_parser("append", help="append changed verdicts and re-sign the head")
    common(add)
    add.add_argument("--key", required=True, help="private ed25519 key (outside the repo)")
    add.add_argument("--signer", required=True)
    add.add_argument("--date", default=None)
    add.set_defaults(func=append)

    args = ap.parse_args()
    args.repo = os.path.abspath(os.path.expanduser(args.repo))

    def inside(value):
        value = os.path.expanduser(value)
        return os.path.abspath(value if os.path.isabs(value)
                               else os.path.join(args.repo, value))

    args.journal = inside(args.journal)
    args.head = inside(args.head)
    args.allowed_signers = inside(args.allowed_signers)
    if args.command == "append":
        args.key = os.path.abspath(os.path.expanduser(args.key))
        if args.date is None:
            args.date = date.today().isoformat()
        if not DATE_RE.match(args.date):
            print("--date must be YYYY-MM-DD, got %r" % args.date, file=sys.stderr)
            return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
