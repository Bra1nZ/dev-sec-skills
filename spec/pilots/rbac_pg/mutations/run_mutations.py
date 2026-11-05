#!/usr/bin/env python3
"""Mutation fixtures for the rbac_pg pilot — verify that the detectors can fail.

Each fixture takes a throw-away copy of the target repository, applies one
source mutation from mutations.yaml, runs the named detector suite, and
compares the set of failing tests with the predicted set.

A fixture passes only when ALL of the following hold:
  * the artifact still matches source_sha256;
  * every anchor occurs exactly once in the artifact;
  * the unmutated baseline (optional, on by default) has 0 FAIL;
  * the mutated run exits non-zero;
  * the set of failing test names equals expect_failures exactly.

Exit codes: 0 all fixtures pass, 1 at least one fixture fails, 2 tool error.

Usage:
    python3 spec/pilots/rbac_pg/mutations/run_mutations.py \
        --target /home/admini/projects/rbac_pg \
        --dsn "postgresql://postgres@127.0.0.1:55433/postgres" \
        --ensure-roles

The target repository is never modified: only a copy under --workdir is.
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

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
FAIL_RE = re.compile(r"^\s*\[FAIL\]\s*(.*)$")
TOTAL_RE = re.compile(r"ИТОГО:\s*(\d+)\s*OK,\s*(\d+)\s*FAIL")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_failures(output):
    names = []
    for raw in output.splitlines():
        line = ANSI_RE.sub("", raw)
        m = FAIL_RE.match(line)
        if m:
            # "name: detail" -> name (details are emitted only for failures)
            names.append(m.group(1).split(": ", 1)[0].strip())
    # Suites print each failure twice: the inline coloured report and a plain
    # summary list at the end. Keep the first occurrence, drop duplicates.
    names = list(dict.fromkeys(names))
    totals = None
    m = TOTAL_RE.search(ANSI_RE.sub("", output))
    if m:
        totals = (int(m.group(1)), int(m.group(2)))
    return names, totals


def ensure_roles(dsn):
    import psycopg2

    conn = psycopg2.connect(dsn, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        DO $$
        DECLARE r TEXT;
        BEGIN
            FOREACH r IN ARRAY ARRAY['rbac_admin', 'rbac_label_admin',
                                     'rbac_auditor', 'rbac_readwrite',
                                     'rbac_readonly'] LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT', r);
                END IF;
            END LOOP;
        END
        $$;
        """
    )
    conn.close()


def prepare_tree(target, workdir, fixture):
    tree = os.path.join(workdir, fixture["id"])
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree)
    for sub in ("setup", "sql"):
        shutil.copytree(os.path.join(target, sub), os.path.join(tree, sub),
                        ignore=shutil.ignore_patterns("__pycache__"))
    return tree


def apply_mutations(path, mutations):
    text = open(path, encoding="utf-8").read()
    for i, mut in enumerate(mutations, 1):
        anchor = mut["anchor"]
        replacement = mut["replacement"]
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError(
                "%s: anchor %d occurs %d times (expected 1): %r"
                % (os.path.basename(path), i, count, anchor[:80])
            )
        text = text.replace(anchor, replacement)
    open(path, "w", encoding="utf-8").write(text)


def run_suite(tree, suite, dsn, timeout):
    env = dict(os.environ, ADMIN_DATABASE_URL=dsn)
    proc = subprocess.run(
        [sys.executable, suite],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="/home/admini/projects/rbac_pg")
    ap.add_argument("--dsn", default=os.getenv("ADMIN_DATABASE_URL"))
    ap.add_argument("--workdir", default="/tmp/opencode/rbac-mutations")
    ap.add_argument("--fixtures", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mutations.yaml"))
    ap.add_argument("--only", action="append", default=None,
                    help="fixture id (repeatable)")
    ap.add_argument("--ensure-roles", action="store_true",
                    help="create the extension's global roles if absent")
    ap.add_argument("--skip-baseline", action="store_true",
                    help="do not run the unmutated control first")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    if not args.dsn:
        ap.error("--dsn or ADMIN_DATABASE_URL is required")
    if not os.path.isdir(args.target):
        ap.error("target repository not found: %s" % args.target)

    doc = yaml.safe_load(open(args.fixtures, encoding="utf-8"))
    fixtures = doc.get("fixtures") or []
    if args.only:
        wanted = set(args.only)
        fixtures = [f for f in fixtures if f["id"] in wanted]
        if not fixtures:
            ap.error("no fixture matched --only")

    os.makedirs(args.workdir, exist_ok=True)
    results_dir = os.path.join(args.workdir, "results")
    os.makedirs(results_dir, exist_ok=True)

    if args.ensure_roles:
        ensure_roles(args.dsn)

    # Preflight: pin every artifact before touching the cluster.
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

    # Baseline: one unmutated run per suite. Proves the mutation is the cause.
    baseline_ok = {}
    if not args.skip_baseline:
        for suite in sorted({fx["suite"] for fx in fixtures}):
            tree = os.path.join(args.workdir, "baseline-" + os.path.basename(suite))
            shutil.rmtree(tree, ignore_errors=True)
            os.makedirs(tree)
            for sub in ("setup", "sql"):
                shutil.copytree(os.path.join(args.target, sub),
                                os.path.join(tree, sub),
                                ignore=shutil.ignore_patterns("__pycache__"))
            rc, out = run_suite(tree, suite, args.dsn, args.timeout)
            fails, totals = parse_failures(out)
            ok = rc == 0 and not fails
            baseline_ok[suite] = ok
            print("BASELINE %-32s %s  %s"
                  % (os.path.basename(suite),
                     "PASS" if ok else "FAIL",
                     "ИТОГО: %d OK, %d FAIL" % totals if totals else "no summary"))
            if not ok:
                open(os.path.join(results_dir,
                                  "baseline-" + os.path.basename(suite) + ".log"),
                     "w", encoding="utf-8").write(out)

    failures = 0
    for fx in fixtures:
        fid = fx["id"]
        if not args.skip_baseline and not baseline_ok.get(fx["suite"], False):
            print("SKIP     %-12s baseline for %s failed" % (fid, fx["suite"]))
            failures += 1
            continue

        tree = prepare_tree(args.target, args.workdir, fx)
        try:
            apply_mutations(os.path.join(tree, fx["artifact"]), fx["mutations"])
        except RuntimeError as e:
            print("FAIL     %-12s %s" % (fid, e))
            failures += 1
            continue

        rc, out = run_suite(tree, fx["suite"], args.dsn, args.timeout)
        log_path = os.path.join(results_dir, fid + ".log")
        open(log_path, "w", encoding="utf-8").write(out)

        actual, totals = parse_failures(out)
        expected = fx["expect_failures"]
        same = (sorted(actual) == sorted(expected))
        ok = rc != 0 and same

        print("FIXTURE  %-12s %-11s %-22s %s  %s"
              % (fid, fx["cell"], fx["detector"],
                 "PASS" if ok else "FAIL",
                 "ИТОГО: %d OK, %d FAIL" % totals if totals else "no summary"))
        if not same:
            for name in expected:
                if name not in actual:
                    print("           missing expected failure: %s" % name)
            for name in actual:
                if name not in expected:
                    print("           unexpected failure:       %s" % name)
        if not ok:
            failures += 1
            print("           log: %s" % log_path)

    total = len(fixtures)
    print("\n%d/%d fixtures matched the predicted failure set"
          % (total - failures, total))
    if failures:
        print("Mutation evidence is INCOMPLETE: %d fixture(s) did not match."
              % failures)
        return 1
    print("Mutation evidence complete: every detector failed exactly where predicted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
