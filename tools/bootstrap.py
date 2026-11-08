#!/usr/bin/env python3
"""Bootstrap a target repository with the dev-sec-skills evidence gates.

The tool is a planner and a generator, not a test runner. It copies the
linters and their data files into the target, writes an honest `open` cell
registry and claim ledger, optionally renders the two GitHub Actions gates and
creates an ed25519 signing key outside the repository.

What it does not do: run the target's tests, invent evidence, or promote a
claim. A generated ledger is `open` with an empty `evidence` list, because
creating a ledger is not evidence that any invariant holds. Promotion is a
separate, recorded step (`docs/onboarding.md`).

Safety rules:

  * the target may not be the source repository or sit inside it;
  * the private anchor key may not sit inside the target or the source;
  * `--force` refreshes vendored tools and rendered CI files, but never
    overwrites a registry or a ledger: those hold evidence, and a bootstrap
    that can erase evidence is a liability;
  * every path comes from an argument or an environment variable; no home
    directory, `/tmp`, or checkout path is hardcoded.

Exit codes: 0 ok (created, unchanged or dry-run), 1 drift or refusal,
2 tool/usage error.

Usage:
    python3 tools/bootstrap.py --target ../service --name service \\
        --suite-glob "tests/*.py" --with-ci --with-anchor

    python3 tools/bootstrap.py --target ../service --dry-run
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.dirname(HERE)

VENDOR_TOOLS = (
    "claim_lint.py",
    "cell_lint.py",
    "status_diff.py",
    "anchor_subject.py",
    "anchor_run.py",
)
VENDOR_TREES = ("styles", "schemas")
VENDOR_EXTRA = ("spec/conveyor/cell-registry.schema.json",)
CI_TEMPLATES = ("claim-lint.yml", "cell-lint.yml")
VERSION_FILE = "tools/dev-sec-skills.VERSION"
README = "README.md"


class Refusal(Exception):
    """A plan the tool will not execute; the message says why."""


# ------------------------------------------------------------------ utilities

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def is_within(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def rel_inside(value, label):
    """A repo-relative path with no escape hatch."""
    if os.path.isabs(value):
        raise Refusal("%s must be relative to the target, got %r" % (label, value))
    norm = os.path.normpath(value)
    if norm == "." or norm.startswith(".." + os.sep) or norm == "..":
        raise Refusal("%s must stay inside the target, got %r" % (label, value))
    return norm


def git(source, *args):
    proc = subprocess.run(["git", "-C", source] + list(args),
                          capture_output=True, text=True)
    return proc


def source_identity(source):
    inside = git(source, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None, None
    head = git(source, "rev-parse", "HEAD")
    commit = head.stdout.strip() if head.returncode == 0 else None
    dirty = None
    status = git(source, "status", "--porcelain", "--untracked-files=no")
    if status.returncode == 0:
        dirty = bool(status.stdout.strip())
    return commit, dirty


def yaml_scalar(value):
    """A YAML scalar that cannot break out of its line.

    JSON strings are valid YAML double-quoted scalars and escape backslashes,
    quotes and control characters, so a value cannot inject a second key.
    """
    if re.match(r"^[A-Za-z0-9_./-]+$", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def set_env_line(text, key, value):
    """Replace one `KEY: value` line and keep its trailing comment."""
    pattern = re.compile(r"(?m)^(\s*%s:)(\s*)(.*?)(\s*#.*)?$" % re.escape(key))
    rendered = yaml_scalar(value)
    replaced, count = pattern.subn(
        lambda m: "%s %s%s" % (m.group(1), rendered, m.group(4) or ""),
        text, count=1)
    if count != 1:
        raise Refusal("CI template has no %s: line" % key)
    return replaced


# ------------------------------------------------------------------- content

def registry_text(name, owner, when):
    return """\
# Cell registry for %(name)s.
#
# One cell is open on purpose. It is the shape of a claim, not coverage: no
# detector has exercised it and no negative test has shown it can fail. Replace
# the example with the invariants this repository must keep, then add a
# detector and a mutation fixture before raising coverage_status.
project: %(name)s
generated: "%(when)s"
taxonomy:
  name: invariant-first-code
  version: "1"
  classes:
    - security
    - correctness
    - maintainability
    - performance
cells:
  - id: CELL-001
    title: The test harness runs to completion and reports one result per discovered test.
    taxonomy_class: maintainability
    failure_class: test-harness-broken
    entry_points: [test, ci]
    failure_mode: detect
    coverage_status: open
    claim_ids: [C-01]
    detectors: []
    residual_risk: A green harness says the tests reported a result; it does not say the assertions
      are relevant to this repository's invariants.
    limitations: The bootstrap creates the shape only. No command has run, no log is captured and
      no detector exists, so this cell cannot support a non-open status.
    owner: %(owner)s
    last_seen: "%(when)s"
""" % {"name": name, "owner": owner, "when": when}


def ledger_text(name, when):
    return """\
# Claim ledger for %(name)s.
#
# Every claim starts open. A status is raised only by adding evidence: a
# command, a committed log, a run_record and an anchor. Creating this file is
# not evidence that any invariant holds.
project: %(name)s
generated: "%(when)s"
claims:
  - id: C-01
    claim: The test harness runs to completion and reports a result for each test it discovers.
    mechanism: Not run yet. The bootstrap created this record; replace the claim with a real
      invariant and record the command that exercises it.
    status: open
    scope:
      platforms: The target repository's own test command; no platform is asserted until a run is
        captured.
      actors_excluded:
        - The bootstrap itself, which writes a ledger but does not execute the target.
        - A harness that reports success without naming or running a test.
    evidence: []
    residual_risk: A harness can report a result for a test that does not exercise the invariant the
      claim names.
    limitations: Open by construction. There is no run, no log, no artifact hash and no anchor, so
      the gate has nothing to check beyond the shape of this record.
""" % {"name": name, "when": when}


def ci_text(source, template, values):
    path = os.path.join(source, "ci", template)
    text = open(path, encoding="utf-8").read()
    # Keep the executable body, replace the "copy this template" header: in the
    # target the file is already copied and its values are already rendered.
    marker = "\nname:"
    if marker in text:
        text = text[text.index(marker) + 1:]
    for key, value in values.items():
        text = set_env_line(text, key, value)
    header = (
        "# Generated by dev-sec-skills bootstrap from ci/%s.\n"
        "# Edit the env block; the rest is the vendored gate. The checkout\n"
        "# actions below use mutable refs: pin them before enabling this gate.\n"
        % template
    )
    return header + text


# --------------------------------------------------------------------- plan

def vendor_tree(source, tree):
    root = os.path.join(source, tree)
    if not os.path.isdir(root):
        raise Refusal("source tree missing: %s" % root)
    files = []
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if tree in ("styles", "schemas") and name == README:
                continue
            absolute = os.path.join(base, name)
            files.append((os.path.relpath(absolute, source), absolute))
    return files


def build_plan(args):
    target = os.path.abspath(args.target)
    source = os.path.abspath(args.source)
    if not os.path.isdir(target):
        raise Refusal("target directory does not exist: %s" % target)
    if is_within(target, source):
        raise Refusal("refusing to bootstrap the source repository or a directory inside it: %s"
                      % target)

    ledger = rel_inside(args.ledger, "--ledger")
    registry = rel_inside(args.registry, "--registry")
    if ledger == registry:
        raise Refusal("--ledger and --registry must be different files")

    # Source files first; the VERSION file hashes exactly these bytes.
    vendor = []
    for name in VENDOR_TOOLS:
        absolute = os.path.join(source, "tools", name)
        if not os.path.isfile(absolute):
            raise Refusal("source tool missing: %s" % absolute)
        vendor.append(("tools/" + name, absolute))
    for tree in VENDOR_TREES:
        vendor.extend(vendor_tree(source, tree))
    for rel in VENDOR_EXTRA:
        absolute = os.path.join(source, rel)
        if not os.path.isfile(absolute):
            raise Refusal("source file missing: %s" % absolute)
        vendor.append((rel, absolute))
    vendor.sort()

    entries = []
    for rel, absolute in vendor:
        entries.append({"rel": rel, "bytes": read_bytes(absolute), "kind": "vendor"})
    version = {
        "schema": 1,
        "source": "dev-sec-skills",
        "source_commit": args.source_commit,
        "source_dirty": args.source_dirty,
        "files": {rel: sha256_bytes(data) for rel, data in
                  ((e["rel"], e["bytes"]) for e in entries)},
    }
    version_bytes = (json.dumps(version, sort_keys=True, indent=2) + "\n").encode("utf-8")
    entries.append({"rel": VERSION_FILE, "bytes": version_bytes, "kind": "vendor"})

    when = args.date
    entries.append({"rel": registry, "kind": "create-only",
                    "bytes": registry_text(args.name, args.owner, when).encode("utf-8")})
    entries.append({"rel": ledger, "kind": "create-only",
                    "bytes": ledger_text(args.name, when).encode("utf-8")})

    if args.with_ci:
        claim_values = {
            "LEDGER": ledger,
            "SUITE_GLOB": args.suite_glob,
            "RELEASE_REF": args.base_ref,
            "FIRST_RELEASE": "1",
        }
        cell_values = {
            "REGISTRY": registry,
            "LEDGER": ledger,
            "SUITE_GLOB": args.suite_glob,
            "BASE_REF": args.base_ref,
            "FIRST_RELEASE": "1",
        }
        entries.append({
            "rel": ".github/workflows/claim-lint.yml", "kind": "ci",
            "bytes": ci_text(source, "claim-lint.yml", claim_values).encode("utf-8")})
        entries.append({
            "rel": ".github/workflows/cell-lint.yml", "kind": "ci",
            "bytes": ci_text(source, "cell-lint.yml", cell_values).encode("utf-8")})

    return target, source, entries, ledger, registry


# ------------------------------------------------------------------- writing

def classify(entry, target, force):
    path = os.path.join(target, entry["rel"])
    if not os.path.exists(path):
        return "create"
    if entry["kind"] == "create-only":
        return "skip"
    if read_bytes(path) == entry["bytes"]:
        return "same"
    if entry["kind"] == "ci" and not force:
        return "drift"
    if entry["kind"] == "vendor":
        return "update" if force else "drift"
    return "skip"


def write_entry(entry, target):
    path = os.path.join(target, entry["rel"])
    os.makedirs(os.path.dirname(path) or target, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(entry["bytes"])
    return path


def prepare_anchor(args, target, source, dry_run=False):
    """Create or reuse a key outside the repository, and commit the public half."""
    anchor_dir = os.path.abspath(os.path.expanduser(args.anchor_dir))
    if is_within(anchor_dir, target):
        raise Refusal("--anchor-dir must stay outside the target: %s" % anchor_dir)
    if is_within(anchor_dir, source):
        raise Refusal("--anchor-dir must stay outside the source repository: %s" % anchor_dir)
    key = os.path.join(anchor_dir, "key")
    action = "reuse" if os.path.exists(key) else "create"
    allowed_rel = rel_inside(args.allowed_signers, "--allowed-signers")
    if dry_run:
        return {
            "action": "would-" + action,
            "key": key,
            "allowed_signers": allowed_rel,
            "fingerprint": "(not created in a dry run)",
            "signer": args.signer,
        }

    os.makedirs(anchor_dir, exist_ok=True)
    if os.path.exists(key):
        if not os.path.exists(key + ".pub"):
            raise Refusal("private key exists without a public half: %s.pub" % key)
    else:
        proc = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", args.signer, "-f", key],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise Refusal("ssh-keygen failed: %s" % (proc.stderr or proc.stdout).strip())

    public = open(key + ".pub", encoding="utf-8").read().strip()
    line = "%s %s\n" % (args.signer, public)
    local_allowed = os.path.join(anchor_dir, "allowed_signers")
    existing = open(local_allowed, encoding="utf-8").read() if os.path.exists(local_allowed) else ""
    if line not in existing.splitlines(True):
        if any(row.split()[0] == args.signer for row in existing.splitlines() if row.split()):
            raise Refusal("signer %r already exists with a different key in %s; rotate it explicitly"
                          % (args.signer, local_allowed))
        with open(local_allowed, "a", encoding="utf-8") as handle:
            handle.write(line)

    allowed_path = os.path.join(target, allowed_rel)
    os.makedirs(os.path.dirname(allowed_path) or target, exist_ok=True)
    if os.path.exists(allowed_path):
        target_text = open(allowed_path, encoding="utf-8").read()
        if line not in target_text.splitlines(True):
            if any(row.split()[0] == args.signer
                   for row in target_text.splitlines() if row.split()):
                raise Refusal("signer %r already exists with a different key in %s"
                              % (args.signer, allowed_path))
            with open(allowed_path, "a", encoding="utf-8") as handle:
                handle.write(line)
    else:
        with open(allowed_path, "w", encoding="utf-8") as handle:
            handle.write(line)

    fingerprint = subprocess.run(["ssh-keygen", "-lf", key + ".pub"],
                                 capture_output=True, text=True)
    return {
        "action": action,
        "key": key,
        "allowed_signers": allowed_rel,
        "fingerprint": fingerprint.stdout.strip() if fingerprint.returncode == 0 else "unknown",
        "signer": args.signer,
    }


# --------------------------------------------------------------------- print

def makefile_snippet(registry, ledger, suite_glob):
    suite = suite_glob or "tests/*.py"
    note = "" if suite_glob else \
        "# TODO: set SUITE_GLOB to the target's test files; L3 cannot resolve IDs without it.\n"
    return """\
PYTHON ?= python3
REGISTRY ?= %(registry)s
LEDGER ?= %(ledger)s
SUITE_GLOB ?= %(suite)s
%(note)s
.PHONY: verify cells claims status
verify: cells claims status

cells:
\t$(PYTHON) tools/cell_lint.py --root . --ledger "$(LEDGER)" \\
\t  --suite-glob "$(SUITE_GLOB)" "$(REGISTRY)"

claims:
\t$(PYTHON) tools/claim_lint.py --root . --suite-glob "$(SUITE_GLOB)" "$(LEDGER)"

# Drop --first-release after the first release tag exists and BASE_REF names it.
status:
\t$(PYTHON) tools/status_diff.py --repo . --ledger "$(LEDGER)" \\
\t  --git-ref v1.0 --first-release
""" % {"registry": registry, "ledger": ledger, "suite": suite, "note": note}


def checklist(args, ledger, registry, anchor):
    key = anchor["key"] if anchor else "$ANCHOR_DIR/key"
    allowed = anchor["allowed_signers"] if anchor else "spec/anchor/allowed_signers"
    signer = anchor["signer"] if anchor else (args.signer or "<signer>")
    rows = [
        "Install the only third-party dependency: pip install pyyaml",
        "Replace CELL-001 in %s with one real invariant and its entry points." % registry,
        "Replace C-01 in %s; keep status: open until a run exists." % ledger,
        "Run the suite with a runner that names each test (pytest -v or unittest -v),\n"
        "   capture stdout+stderr to a committed log, and add a run_record with its SHA-256.",
        ("Sign the record, then paste the printed anchor block into the run_record:\n"
         "   python3 tools/anchor_run.py create --ledger %s --claim C-01 \\\n"
         "     --channel run-record --run 0 --key %s --signer %s \\\n"
         "     --out-dir spec/anchor --allowed-signers %s --id <stable-id> --base ."
         % (ledger, key, signer, allowed)),
        "Only then raise the claim and the cell to tested, in the same commit as the evidence.",
        "Run every gate; a warning is visible, an error blocks: make verify",
        "What a green gate does not prove: the key holder can re-sign, replacing "
        "allowed_signers plus a new signature bypasses the check, and no transparency "
        "log or timestamping exists (C-13). A green gate is consistency, not a certificate.",
    ]
    return "\n".join("  %d. %s" % (i + 1, row) for i, row in enumerate(rows))


def main():
    ap = argparse.ArgumentParser(
        description="Bootstrap a target repository with the dev-sec-skills gates")
    ap.add_argument("--target", required=True, help="existing target repository directory")
    ap.add_argument("--name", help="project name written into the templates "
                                   "(default: target directory name)")
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="dev-sec-skills checkout to vendor from (default: this checkout)")
    ap.add_argument("--suite-glob", default="",
                    help='glob for the target test suite, e.g. "tests/*.py"')
    ap.add_argument("--ledger", default="docs/claims.yaml",
                    help="target-relative claim ledger path (default: docs/claims.yaml)")
    ap.add_argument("--registry", default="spec/cells.yaml",
                    help="target-relative cell registry path (default: spec/cells.yaml)")
    ap.add_argument("--owner", default="unassigned",
                    help="owner written into the example cell (default: unassigned)")
    ap.add_argument("--with-ci", action="store_true",
                    help="render .github/workflows/{claim,cell}-lint.yml")
    ap.add_argument("--with-anchor", action="store_true",
                    help="create/reuse an ed25519 key outside the target and commit allowed_signers")
    ap.add_argument("--anchor-dir",
                    default=os.environ.get("DEV_SEC_SKILLS_ANCHOR_DIR",
                                           os.path.expanduser("~/.config/dev-sec-skills/anchor")),
                    help="private anchor key directory (env DEV_SEC_SKILLS_ANCHOR_DIR)")
    ap.add_argument("--signer", help="anchor signer name (default: <name>-anchor-<date>)")
    ap.add_argument("--allowed-signers", default="spec/anchor/allowed_signers",
                    help="target-relative committed public keys (default: spec/anchor/allowed_signers)")
    ap.add_argument("--base-ref", default="v1.0",
                    help="release ref rendered into the CI gates (default: v1.0)")
    ap.add_argument("--date", default=date.today().isoformat(),
                    help="date written into the templates (default: today)")
    ap.add_argument("--force", action="store_true",
                    help="refresh vendored tools and CI files; never the registry or ledger")
    ap.add_argument("--dry-run", action="store_true", help="print the plan without writing")
    args = ap.parse_args()

    target_hint = os.path.abspath(os.path.expanduser(args.target))
    if not args.name:
        args.name = os.path.basename(target_hint.rstrip(os.sep)) or "target"
    if not re.match(r"^[A-Za-z0-9._/-]+$", args.name):
        print("error: --name may only contain letters, digits, '.', '_', '/' and '-'",
              file=sys.stderr)
        return 2
    if not args.signer:
        args.signer = "%s-anchor-%s" % (re.sub(r"[^A-Za-z0-9._-]+", "-", args.name), args.date)
    if not re.match(r"^[A-Za-z0-9._@-]+$", args.signer):
        print("error: --signer may only contain letters, digits, '.', '_', '@' and '-'",
              file=sys.stderr)
        return 2

    try:
        args.source_commit, args.source_dirty = source_identity(os.path.abspath(args.source))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
            raise Refusal("--date must be YYYY-MM-DD, got %r" % args.date)
        target, source, entries, ledger, registry = build_plan(args)
        states = [(entry, classify(entry, target, args.force)) for entry in entries]
        anchor = (prepare_anchor(args, target, source, args.dry_run)
                  if args.with_anchor else None)
    except Refusal as exc:
        print("bootstrap: %s" % exc, file=sys.stderr)
        return 2

    counts = {}
    for entry, state in states:
        counts[state] = counts.get(state, 0) + 1
        label = {"create": "create ", "update": "update ", "same": "same   ",
                 "skip": "skip   ", "drift": "DRIFT  "}[state]
        print("  %s %s" % (label, entry["rel"]))

    drift = [entry["rel"] for entry, state in states if state == "drift"]
    if not args.dry_run:
        for entry, state in states:
            if state in ("create", "update"):
                write_entry(entry, target)
        if anchor:
            print("  anchor %s %s (%s)" % (anchor["action"], anchor["signer"],
                                           anchor["fingerprint"]))

    print("bootstrap: %d file(s) | %s" % (
        len(entries), ", ".join("%s=%d" % (k, counts[k]) for k in
                                ("create", "update", "same", "skip", "drift") if k in counts)))
    if args.source_dirty:
        print("warning: the source checkout is dirty; the vendored bytes come from a worktree, "
              "not from %s" % (args.source_commit or "a commit"), file=sys.stderr)
    if args.with_ci:
        print("warning: the CI templates use mutable action refs (actions/checkout@v4, "
              "actions/setup-python@v5); pin them before enabling the gate.", file=sys.stderr)
    if drift:
        print("bootstrap: %d drift file(s); re-run with --force to refresh vendored bytes: %s"
              % (len(drift), ", ".join(drift)), file=sys.stderr)
        if not args.force and not args.dry_run:
            return 1

    if args.dry_run:
        print("dry run: no files were written")
        return 0

    print("\nMakefile snippet (copy into the target Makefile):\n")
    print(makefile_snippet(registry, ledger, args.suite_glob))
    print("Checklist:\n")
    print(checklist(args, ledger, registry, anchor))
    return 0


if __name__ == "__main__":
    sys.exit(main())
