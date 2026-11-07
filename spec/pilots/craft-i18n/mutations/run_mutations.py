#!/usr/bin/env python3
"""Mutation fixtures for the craft-i18n pilot — verify that the detectors can fail.

Each fixture takes a throw-away copy of the target repository, applies one
source mutation from mutations.yaml, runs the checker suite, and compares the
set of failing tests with the predicted set.

A fixture passes only when ALL of the following hold:
  * the artifact still matches source_sha256;
  * every anchor occurs exactly once in the artifact;
  * the unmutated baseline (optional, on by default) exits 0 with no failures;
  * the mutated run exits non-zero;
  * the set of failing test names equals expect_failures exactly.

Rust names are normalised: `catalog::tests::foo` and `locales::foo` are
compared as `foo`, so a fixture predicts the test, not its module path.

Exit codes: 0 all fixtures pass, 1 at least one fixture fails, 2 tool error.

Usage:
    python3 spec/pilots/craft-i18n/mutations/run_mutations.py \
        --target /home/admini/projects/astraoffice/craft-i18n

The target repository is never modified: only a copy under --workdir is.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
FAIL_NAME_RE = re.compile(r"^\s{4}(\S+)\s*$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_failures(output):
    """Failing test names from cargo test output, module prefixes stripped."""
    names = set()
    in_failures = False
    for raw in output.splitlines():
        line = ANSI_RE.sub("", raw).rstrip()
        stripped = line.strip()
        if stripped == "failures:":
            in_failures = True
            continue
        if not in_failures:
            continue
        if stripped.startswith("test result:") or not stripped:
            in_failures = False
            continue
        m = FAIL_NAME_RE.match(line)
        if m:
            names.add(m.group(1).rsplit("::", 1)[-1])
    return names


def apply_mutations(path, mutations):
    text = open(path, encoding="utf-8").read()
    for i, mut in enumerate(mutations, 1):
        anchor = mut["anchor"]
        replacement = mut["replacement"]
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError(
                "%s: anchor %d occurs %d times (expected 1): %r"
                % (os.path.basename(path), i, count, anchor[:80]))
        text = text.replace(anchor, replacement)
    open(path, "w", encoding="utf-8").write(text)


def prepare_tree(target, workdir, fixture_id):
    tree = os.path.join(workdir, fixture_id)
    shutil.rmtree(tree, ignore_errors=True)
    # copy_function=shutil.copy, not copy2: a preserved old mtime is older than
    # the shared target dir's fingerprint, so cargo would reuse the previous
    # fixture's mutated artifact. Fresh mtimes force a rebuild from this copy.
    shutil.copytree(target, tree, copy_function=shutil.copy,
                    ignore=shutil.ignore_patterns("target", ".git"))
    return tree


def run_suite(tree, argv, target_dir, timeout):
    env = dict(os.environ, CARGO_TARGET_DIR=target_dir)
    env.setdefault("CARGO_TERM_COLOR", "never")
    proc = subprocess.run(argv, cwd=tree, env=env, capture_output=True,
                          text=True, timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="/home/admini/projects/astraoffice/craft-i18n")
    ap.add_argument("--fixtures", default=os.path.join(here, "mutations.yaml"))
    ap.add_argument("--workdir", default="/tmp/opencode/craft-i18n-mutations")
    ap.add_argument("--target-dir", default="/tmp/opencode/craft-i18n-target",
                    help="shared CARGO_TARGET_DIR; the mutated crate is rebuilt by content")
    ap.add_argument("--only", action="append", default=None,
                    help="fixture id (repeatable)")
    ap.add_argument("--only-cell", action="append", default=None,
                    help="cell id (repeatable); selects every fixture for the cell")
    ap.add_argument("--plan", default=None,
                    help="JSON plan from tools/mutation_plan.py; an empty plan "
                         "runs nothing and exits 0 (V2-11)")
    ap.add_argument("--skip-baseline", action="store_true",
                    help="do not run the unmutated control first")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    if not os.path.isdir(args.target):
        ap.error("target repository not found: %s" % args.target)

    doc = yaml.safe_load(open(args.fixtures, encoding="utf-8"))
    fixtures = doc.get("fixtures") or []
    command = doc.get("command") or ["cargo", "test", "--offline",
                                     "-p", "craft-i18n-tests"]
    if args.plan:
        try:
            with open(args.plan, encoding="utf-8") as f:
                plan = json.load(f)
        except (OSError, ValueError) as exc:
            ap.error("cannot read plan %s: %s" % (args.plan, exc))
        planned = {item.get("fixture") for item in plan.get("selected") or []}
        fixtures = [f for f in fixtures if f["id"] in planned]
        if not fixtures:
            print("plan selected no fixtures; nothing to run")
            return 0
    if args.only:
        wanted = set(args.only)
        fixtures = [f for f in fixtures if f["id"] in wanted]
        if not fixtures:
            ap.error("no fixture matched --only")
    if args.only_cell:
        wanted_cells = set(args.only_cell)
        fixtures = [f for f in fixtures if f.get("cell") in wanted_cells]
        if not fixtures:
            ap.error("no fixture matched --only-cell")

    os.makedirs(args.workdir, exist_ok=True)
    results_dir = os.path.join(args.workdir, "results")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(args.target_dir, exist_ok=True)

    # Preflight: pin every artifact before copying anything.
    for fx in fixtures:
        path = os.path.join(args.target, fx["artifact"])
        if not os.path.exists(path):
            print("PREFLIGHT FAIL %s: missing %s" % (fx["id"], path))
            return 2
        actual = sha256(path)
        if actual != fx["source_sha256"]:
            print("PREFLIGHT FAIL %s: %s sha256 %s != pinned %s"
                  % (fx["id"], fx["artifact"], actual, fx["source_sha256"]))
            return 2

    baseline_ok = True
    if not args.skip_baseline:
        tree = prepare_tree(args.target, args.workdir, "baseline")
        rc, out = run_suite(tree, command, args.target_dir, args.timeout)
        fails = parse_failures(out)
        baseline_ok = rc == 0 and not fails
        print("BASELINE %-32s %s  exit=%d  failures=%s"
              % (os.path.basename(args.target),
                 "PASS" if baseline_ok else "FAIL", rc,
                 ",".join(sorted(fails)) or "none"))
        open(os.path.join(results_dir, "baseline.log"), "w",
             encoding="utf-8").write(out)
        if not baseline_ok:
            print("error: unmutated baseline is not green; fixtures would prove nothing",
                  file=sys.stderr)
            return 2

    failures = 0
    for fx in fixtures:
        fid = fx["id"]
        tree = prepare_tree(args.target, args.workdir, fid)
        try:
            apply_mutations(os.path.join(tree, fx["artifact"]), fx["mutations"])
        except RuntimeError as e:
            print("FAIL     %-12s %s" % (fid, e))
            failures += 1
            continue

        try:
            rc, out = run_suite(tree, command, args.target_dir, args.timeout)
        except subprocess.TimeoutExpired:
            print("FAIL     %-12s timeout after %ds" % (fid, args.timeout))
            failures += 1
            continue
        open(os.path.join(results_dir, fid + ".log"), "w",
             encoding="utf-8").write(out)

        got = parse_failures(out)
        want = set(fx.get("expect_failures") or [])
        ok = rc != 0 and got == want
        print("FIXTURE  %-12s %-11s %-18s %s"
              % (fid, fx["cell"], fx["detector"], "PASS" if ok else "FAIL"))
        if not ok:
            failures += 1
            print("           exit=%d expected non-zero" % rc)
            if got != want:
                print("           failing set: got %s, expected %s"
                      % (sorted(got) or "none", sorted(want) or "none"))
            print("           log: %s" % os.path.join(results_dir, fid + ".log"))

    print("fixtures: %d/%d matched" % (len(fixtures) - failures, len(fixtures)))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
