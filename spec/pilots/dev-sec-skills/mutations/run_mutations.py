#!/usr/bin/env python3
"""Mutation fixtures for the dev-sec-skills self-pilot.

The detector claims that it rejects a mutable action reference. This runner
proves the claim is falsifiable: it copies a clean probe workflow tree,
applies one mutation from mutations.yaml, runs the detector against the copy,
and requires the set of failing detector tests to equal `expect_failures`
exactly.

A fixture passes only when ALL of the following hold:
  * the probe artifact still matches source_sha256;
  * every anchor occurs exactly once in the artifact;
  * the unmutated baseline (on by default) exits 0 with no failures;
  * the mutated run exits non-zero;
  * the set of failing test names equals expect_failures exactly.

The repository is never modified: only a copy under --workdir is.

Usage:
    python3 spec/pilots/dev-sec-skills/mutations/run_mutations.py

Exit codes: 0 all fixtures pass, 1 at least one fixture fails, 2 tool error.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

FAIL_RE = re.compile(r"^(\S+) \.\.\. failed$")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_failures(output):
    names = set()
    for raw in output.splitlines():
        match = FAIL_RE.match(raw.strip())
        if match:
            names.add(match.group(1))
    return names


def apply_mutations(path, mutations):
    text = open(path, encoding="utf-8").read()
    for index, mutation in enumerate(mutations, 1):
        anchor = mutation["anchor"]
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError("%s: anchor %d occurs %d times (expected 1): %r"
                               % (os.path.basename(path), index, count, anchor[:80]))
        text = text.replace(anchor, mutation["replacement"])
    open(path, "w", encoding="utf-8").write(text)


def prepare_tree(probe, workdir, fixture_id):
    tree = os.path.join(workdir, fixture_id)
    shutil.rmtree(tree, ignore_errors=True)
    shutil.copytree(probe, tree)
    return tree


def run_detector(tree, detector, timeout):
    env = dict(os.environ)
    env["DEVSEC_WORKFLOWS_ROOT"] = os.path.join(tree, ".github", "workflows")
    proc = subprocess.run([sys.executable, detector], env=env, capture_output=True,
                          text=True, timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default=repo,
                        help="repository root that contains the probes (read-only)")
    parser.add_argument("--fixtures", default=os.path.join(here, "mutations.yaml"))
    parser.add_argument("--workdir", default="/tmp/opencode/dev-sec-skills-mutations")
    parser.add_argument("--only", action="append", default=None,
                        help="fixture id (repeatable)")
    parser.add_argument("--skip-baseline", action="store_true",
                        help="do not run the unmutated control first")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if not os.path.isdir(args.target):
        parser.error("target repository not found: %s" % args.target)

    doc = yaml.safe_load(open(args.fixtures, encoding="utf-8"))
    fixtures = doc.get("fixtures") or []
    detector = os.path.join(args.target, doc["detector"])
    if not os.path.exists(detector):
        parser.error("detector not found: %s" % detector)
    if args.only:
        wanted = set(args.only)
        fixtures = [f for f in fixtures if f["id"] in wanted]
        if not fixtures:
            parser.error("no fixture matched --only")

    os.makedirs(args.workdir, exist_ok=True)
    results_dir = os.path.join(args.workdir, "results")
    os.makedirs(results_dir, exist_ok=True)

    for fixture in fixtures:
        probe = os.path.join(args.target, fixture["probe"])
        artifact = os.path.join(probe, fixture["artifact"])
        if not os.path.exists(artifact):
            print("PREFLIGHT FAIL %s: missing %s" % (fixture["id"], artifact))
            return 2
        actual = sha256(artifact)
        if actual != fixture["source_sha256"]:
            print("PREFLIGHT FAIL %s: %s sha256 %s != pinned %s"
                  % (fixture["id"], fixture["artifact"], actual, fixture["source_sha256"]))
            return 2

    if not args.skip_baseline:
        tree = prepare_tree(os.path.join(args.target, fixtures[0]["probe"]),
                            args.workdir, "baseline")
        try:
            rc, out = run_detector(tree, detector, args.timeout)
        except subprocess.TimeoutExpired:
            print("BASELINE timeout after %ds" % args.timeout)
            return 2
        failures = parse_failures(out)
        baseline_ok = rc == 0 and not failures
        print("BASELINE %-32s %s  exit=%d  failures=%s"
              % (os.path.basename(args.target), "PASS" if baseline_ok else "FAIL",
                 rc, ",".join(sorted(failures)) or "none"))
        open(os.path.join(results_dir, "baseline.log"), "w",
             encoding="utf-8").write(out)
        if not baseline_ok:
            print("error: unmutated baseline is not green; fixtures would prove nothing",
                  file=sys.stderr)
            return 2

    failures = 0
    for fixture in fixtures:
        fixture_id = fixture["id"]
        tree = prepare_tree(os.path.join(args.target, fixture["probe"]),
                            args.workdir, fixture_id)
        try:
            apply_mutations(os.path.join(tree, fixture["artifact"]), fixture["mutations"])
        except RuntimeError as exc:
            print("FAIL     %-12s %s" % (fixture_id, exc))
            failures += 1
            continue

        try:
            rc, out = run_detector(tree, detector, args.timeout)
        except subprocess.TimeoutExpired:
            print("FAIL     %-12s timeout after %ds" % (fixture_id, args.timeout))
            failures += 1
            continue
        open(os.path.join(results_dir, fixture_id + ".log"), "w",
             encoding="utf-8").write(out)

        got = parse_failures(out)
        want = set(fixture.get("expect_failures") or [])
        ok = rc != 0 and got == want
        print("FIXTURE  %-12s %-11s %-18s %s"
              % (fixture_id, fixture["cell"], fixture["detector"],
                 "PASS" if ok else "FAIL"))
        if not ok:
            failures += 1
            print("           exit=%d expected non-zero" % rc)
            if got != want:
                print("           failing set: got %s, expected %s"
                      % (sorted(got) or "none", sorted(want) or "none"))
            print("           log: %s" % os.path.join(results_dir, fixture_id + ".log"))

    print("fixtures: %d/%d matched" % (len(fixtures) - failures, len(fixtures)))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
