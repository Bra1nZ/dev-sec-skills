"""Canonical subject for a static-analysis anchor (C-13).

An anchor is useful only if the signed bytes are a deterministic function of
the record. This module defines that function once; `tools/anchor_run.py`
signs its output and `tools/claim_lint.py` recomputes it during L2. If the two
drifted, a signature would verify against bytes that no longer describe the
record, which is the failure the anchor exists to prevent.

The subject is canonical JSON: sorted keys, no insignificant whitespace, one
trailing newline. It covers the fields a forger would change to move a finding
or its decision: engine and command, the rule set hash, target commit, both
output hashes, exit code, timestamps, status, and the full triage list. It
deliberately excludes the anchor block itself, so adding or replacing an
anchor cannot change what was signed.
"""

import hashlib
import json

ANCHOR_FIELDS = (
    "tool", "version", "command", "rules", "target_commit",
    "output_sha256", "report_sha256", "exit_code",
    "started_at", "finished_at", "status", "triage",
)
RULE_FIELDS = ("name", "source", "sha256")
TRIAGE_FIELDS = ("finding", "disposition", "cell", "detector", "fixture",
                 "reason", "date", "note")


def canonical_subject(run):
    """The dict an anchor signs. Missing optional fields are omitted, not None."""
    subject = {}
    for field in ANCHOR_FIELDS:
        value = run.get(field)
        if value is None:
            continue
        if field == "rules":
            rules = value if isinstance(value, dict) else {}
            value = {key: rules.get(key) for key in RULE_FIELDS
                     if rules.get(key) is not None}
        elif field == "triage":
            entries = []
            for entry in value if isinstance(value, list) else []:
                if not isinstance(entry, dict):
                    continue
                clean = {key: entry.get(key) for key in TRIAGE_FIELDS
                         if entry.get(key) is not None}
                entries.append(clean)
            value = entries
        subject[field] = value
    return subject


def subject_bytes(run):
    """Canonical bytes to sign and, during L2, to recompute."""
    text = json.dumps(canonical_subject(run), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def subject_sha256(run):
    return hashlib.sha256(subject_bytes(run)).hexdigest()
