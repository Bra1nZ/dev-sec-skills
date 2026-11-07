"""Canonical subject for an evidence anchor (C-13).

An anchor is useful only if the signed bytes are a deterministic function of
the record. This module defines that function once; `tools/anchor_run.py`
signs its output and `tools/claim_lint.py` recomputes it during L2. If the two
drifted, a signature would verify against bytes that no longer describe the
record, which is the failure the anchor exists to prevent.

Three channels are anchored, each under its own signature namespace:
`static-analysis` (V2-36), `run-record` (V2-01/V2-02) and `sanitizer`
(V2-35). A signature made in one namespace does not verify in another.

The subject is canonical JSON: sorted keys, no insignificant whitespace, one
trailing newline. It covers the fields a forger would change to move a finding
or its decision: engine and command, the rule set hash, target commit, both
output hashes, exit code, timestamps, status, the cells registry a `covered`
entry resolves against, and the full triage list. It deliberately excludes the
anchor block itself, so adding or replacing an anchor cannot change what was
signed.
"""

import hashlib
import json

ANCHOR_FIELDS = (
    "tool", "version", "command", "rules", "target_commit",
    "output_sha256", "report_sha256", "exit_code",
    "started_at", "finished_at", "status", "cells", "triage",
)
RULE_FIELDS = ("name", "source", "sha256")
TRIAGE_FIELDS = ("finding", "disposition", "cell", "detector", "fixture",
                 "reason", "date", "note")

# Run record (V2-01/V2-02): a test run's identity is its runner, command,
# commit, exit code, timestamps, log hash, optional artifact hash and counts.
# The log path is not signed; the hash is.
RUN_RECORD_FIELDS = (
    "runner", "command", "commit", "exit_code", "started_at", "finished_at",
    "log_sha256", "artifact_sha256", "tests_run", "tests_passed",
)
# Sanitizer run (V2-35): what instrumented the build, under which flags, what
# it printed (by hash) and how it ended.
SANITIZER_FIELDS = (
    "tool", "version", "build_flags", "command", "exit_code",
    "started_at", "finished_at", "output_sha256", "status",
)

# A namespace is the signature's domain: a signature made for one channel does
# not verify under another, even with the same key. L1 enforces the namespace
# per channel.
NAMESPACES = {
    "static-analysis": "dev-sec-skills-static-analysis",
    "run-record": "dev-sec-skills-run-record",
    "sanitizer": "dev-sec-skills-sanitizer",
}


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


def _bytes_of(subject):
    text = json.dumps(subject, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def subject_bytes(run):
    """Canonical bytes of a static-analysis run (sign and, in L2, recompute)."""
    return _bytes_of(canonical_subject(run))


def canonical_run_record_subject(record):
    """The dict an anchor signs for a test run record."""
    if not isinstance(record, dict):
        record = {}
    return {key: record.get(key) for key in RUN_RECORD_FIELDS
            if record.get(key) is not None}


def run_record_subject_bytes(record):
    return _bytes_of(canonical_run_record_subject(record))


def canonical_sanitizer_subject(record):
    """The dict an anchor signs for a sanitizer run."""
    if not isinstance(record, dict):
        record = {}
    return {key: record.get(key) for key in SANITIZER_FIELDS
            if record.get(key) is not None}


def sanitizer_subject_bytes(record):
    return _bytes_of(canonical_sanitizer_subject(record))


def record_subject_bytes(channel, record):
    """Canonical bytes for a named evidence channel."""
    if channel == "static-analysis":
        return subject_bytes(record)
    if channel == "run-record":
        return run_record_subject_bytes(record)
    if channel == "sanitizer":
        return sanitizer_subject_bytes(record)
    raise ValueError("unknown anchor channel: %r" % (channel,))


def subject_sha256(run):
    return hashlib.sha256(subject_bytes(run)).hexdigest()
