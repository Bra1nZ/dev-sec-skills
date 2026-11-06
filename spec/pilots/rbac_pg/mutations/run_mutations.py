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
        --dsn "postgresql://postgres@127.0.0.1:55434/postgres" \
        --ensure-roles \
        --sharedir /tmp/opencode/pgmut/usr/share/postgresql/15/extension

The target repository is never modified: only a copy under --workdir is.
Fixtures with `deploy: sharedir` install the mutated extension files into the
writable sharedir and restore the previous bytes in a finally block.
"""

import argparse
import glob
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
TOTAL_RE = re.compile(r"(?:ИТОГО|ИТОГ|Итог):\s*(\d+)\s*OK,\s*(\d+)\s*FAIL")
SUMMARY_HEADER_RE = re.compile(r"^\s*(?:Провалены|Провалено):\s*$")
SUMMARY_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")
SUMMARY_FAIL_RE = re.compile(r"^\s*\[FAIL\]\s+(.*)$")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_failures(output):
    """Return (failure names, totals) from a detector suite's output.

    Read the plain summary at the end, not the inline lines: an inline report
    appends a free-form detail, and assertion names themselves contain colons
    ("F7f канал 2: ..."). Splitting on the first colon therefore truncates the
    expected name. The summary prints each name exactly once, after the total.
    """
    lines = [ANSI_RE.sub("", raw) for raw in output.splitlines()]
    totals = None
    total_idx = None
    for i, line in enumerate(lines):
        m = TOTAL_RE.search(line)
        if m:
            totals = (int(m.group(1)), int(m.group(2)))
            total_idx = i

    names = []
    if total_idx is not None:
        # Some suites print the failure list directly after the total, with no
        # "Провалены:" header (test_v15_ceiling_trigger.py, test_v151_ranges.py).
        # Start in the failure block and leave it again on any other unindented
        # section header (test_side_channels.py prints "Пробелы ...:" first,
        # whose bullet items are recorded gaps, not failures).
        in_failures = True
        for line in lines[total_idx + 1:]:
            if SUMMARY_HEADER_RE.match(line):
                in_failures = True
                continue
            m = SUMMARY_FAIL_RE.match(line)
            if m:
                names.append(m.group(1).strip())
                continue
            if line and not line[0].isspace() and line.rstrip().endswith(':'):
                in_failures = False
                continue
            if in_failures:
                m = SUMMARY_ITEM_RE.match(line)
                if m:
                    names.append(m.group(1).strip())

    if not names:
        # Fallback for a suite that crashed before its summary: inline lines.
        # Names may then carry a detail suffix, so such a run is not a clean
        # proof; the caller sees "no summary" and the fixture is reviewed.
        for line in lines:
            m = FAIL_RE.match(line)
            if m:
                names.append(m.group(1).strip())

    return list(dict.fromkeys(names)), totals


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


def run_post_sql(dsn, fixture):
    """Run the fixture's cleanup statements against the cluster.

    Mutations that change cluster-wide role attributes would otherwise leak
    into later fixtures: the install script only creates roles ``IF NOT
    EXISTS`` and never reconciles them. ``post_sql`` restores the attributes
    explicitly, and runs in a ``finally`` so a crashing suite cannot leave a
    LOGIN administration role behind.
    """
    statements = fixture.get("post_sql") or []
    if not statements:
        return
    import psycopg2

    conn = psycopg2.connect(dsn, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for sql in statements:
            cur.execute(sql)
    finally:
        conn.close()


def prepare_tree(target, workdir, fixture):
    tree = os.path.join(workdir, fixture["id"])
    shutil.rmtree(tree, ignore_errors=True)
    os.makedirs(tree)
    for sub in ("setup", "sql"):
        shutil.copytree(os.path.join(target, sub), os.path.join(tree, sub),
                        ignore=shutil.ignore_patterns("__pycache__"))
    control = os.path.join(target, "rbac.control")
    if os.path.exists(control):
        shutil.copyfile(control, os.path.join(tree, "rbac.control"))
    for sub in fixture.get("copy_dirs") or []:
        src = os.path.join(target, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tree, sub),
                            ignore=shutil.ignore_patterns("__pycache__"))
        elif os.path.exists(src):
            shutil.copyfile(src, os.path.join(tree, sub))
    return tree


def rbac_deploy_files(tree):
    names = ["rbac.control"]
    names += sorted(os.path.basename(p)
                    for p in glob.glob(os.path.join(tree, "sql", "rbac--*.sql")))
    return names


def deploy_sharedir(tree, sharedir):
    """Install the tree's rbac extension files into a writable sharedir.

    Returns a snapshot of the previous bytes so the caller can restore the
    directory even when the suite crashes.
    """
    snap = {}
    for name in rbac_deploy_files(tree):
        dst = os.path.join(sharedir, name)
        snap[name] = open(dst, "rb").read() if os.path.exists(dst) else None
        src = (os.path.join(tree, "rbac.control") if name == "rbac.control"
               else os.path.join(tree, "sql", name))
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o644)
    return snap


def restore_sharedir(snap, sharedir):
    for name, data in snap.items():
        dst = os.path.join(sharedir, name)
        if data is None:
            if os.path.exists(dst):
                os.unlink(dst)
        else:
            with open(dst, "wb") as f:
                f.write(data)
            os.chmod(dst, 0o644)


def run_command(tree, argv, timeout):
    proc = subprocess.run(argv, cwd=tree, capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, proc.stdout + proc.stderr


def expand_argv(argv, target):
    """Substitute {target} so a copied linter can still resolve the real repo.

    A command fixture runs inside the throw-away tree. Some tools need the
    project root (artifact paths, ``git cat-file`` for evidence commits); the
    copy has neither ``.git`` nor the untouched docs. ``{target}`` therefore
    expands to the original repository passed with ``--target``.
    """
    return [str(a).replace("{target}", target) for a in argv]


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
    ap.add_argument("--sharedir", default=os.getenv("RBAC_SHAREDIR"),
                    help="writable extension dir for deploy: sharedir fixtures "
                         "(default: $RBAC_SHAREDIR)")
    args = ap.parse_args()

    if not os.path.isdir(args.target):
        ap.error("target repository not found: %s" % args.target)

    doc = yaml.safe_load(open(args.fixtures, encoding="utf-8"))
    fixtures = doc.get("fixtures") or []
    if args.only:
        wanted = set(args.only)
        fixtures = [f for f in fixtures if f["id"] in wanted]
        if not fixtures:
            ap.error("no fixture matched --only")

    if any(fx.get("mode") != "command" for fx in fixtures) and not args.dsn:
        ap.error("--dsn or ADMIN_DATABASE_URL is required")
    if any(fx.get("deploy") == "sharedir" for fx in fixtures):
        if not args.sharedir:
            ap.error("--sharedir or RBAC_SHAREDIR is required for sharedir fixtures")
        if not os.path.isdir(args.sharedir):
            ap.error("sharedir not found: %s" % args.sharedir)

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
    suite_fixtures = [fx for fx in fixtures if fx.get("mode") != "command"]
    command_fixtures = [fx for fx in fixtures if fx.get("mode") == "command"]
    baseline_ok = {}
    if not args.skip_baseline:
        for suite in sorted({fx["suite"] for fx in suite_fixtures}):
            tree = os.path.join(args.workdir, "baseline-" + os.path.basename(suite))
            shutil.rmtree(tree, ignore_errors=True)
            os.makedirs(tree)
            for sub in ("setup", "sql"):
                shutil.copytree(os.path.join(args.target, sub),
                                os.path.join(tree, sub),
                                ignore=shutil.ignore_patterns("__pycache__"))
            control = os.path.join(args.target, "rbac.control")
            if os.path.exists(control):
                shutil.copyfile(control, os.path.join(tree, "rbac.control"))

            needs_sharedir = any(
                fx.get("deploy") == "sharedir"
                for fx in suite_fixtures if fx["suite"] == suite)
            try:
                snap = deploy_sharedir(tree, args.sharedir) if needs_sharedir else None
                try:
                    rc, out = run_suite(tree, suite, args.dsn, args.timeout)
                finally:
                    if snap is not None:
                        restore_sharedir(snap, args.sharedir)
            except Exception as e:  # noqa: BLE001 - report, do not abort the batch
                print("BASELINE %-32s FAIL  %s"
                      % (os.path.basename(suite), e))
                baseline_ok[suite] = False
                continue

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

        for fx in command_fixtures:
            tree = prepare_tree(args.target, args.workdir, fx)
            rc, out = run_command(tree, expand_argv(fx["command"], args.target),
                                  args.timeout)
            want = fx.get("baseline_expect_exit", 0)
            absent = fx.get("expect_stdout_contains") or []
            ok = rc == want and not any(s in out for s in absent)
            baseline_ok[fx["id"]] = ok
            print("BASELINE %-32s %s  exit=%d"
                  % (fx["id"], "PASS" if ok else "FAIL", rc))
            if not ok:
                open(os.path.join(results_dir, "baseline-" + fx["id"] + ".log"),
                     "w", encoding="utf-8").write(out)

    failures = 0
    for fx in fixtures:
        fid = fx["id"]
        key = fid if fx.get("mode") == "command" else fx["suite"]
        if not args.skip_baseline and not baseline_ok.get(key, False):
            print("SKIP     %-12s baseline %s failed" % (fid, key))
            failures += 1
            continue

        tree = prepare_tree(args.target, args.workdir, fx)
        try:
            apply_mutations(os.path.join(tree, fx["artifact"]), fx["mutations"])
        except RuntimeError as e:
            print("FAIL     %-12s %s" % (fid, e))
            failures += 1
            continue

        if fx.get("mode") == "command":
            rc, out = run_command(tree, expand_argv(fx["command"], args.target),
                                  args.timeout)
            open(os.path.join(results_dir, fid + ".log"), "w",
                 encoding="utf-8").write(out)
            want = fx.get("expect_exit", 1)
            missing = [s for s in (fx.get("expect_stdout_contains") or [])
                       if s not in out]
            ok = rc == want and not missing
            print("FIXTURE  %-12s %-11s %-22s %s  exit=%d"
                  % (fid, fx["cell"], fx["detector"],
                     "PASS" if ok else "FAIL", rc))
            if missing:
                for s in missing:
                    print("           missing expected output: %s" % s)
            if not ok:
                failures += 1
                print("           log: %s" % os.path.join(results_dir, fid + ".log"))
            continue

        snap = deploy_sharedir(tree, args.sharedir) \
            if fx.get("deploy") == "sharedir" else None
        try:
            rc, out = run_suite(tree, fx["suite"], args.dsn, args.timeout)
        except Exception as e:  # noqa: BLE001 - report, do not abort the batch
            print("FAIL     %-12s run error: %s" % (fid, e))
            failures += 1
            continue
        finally:
            if snap is not None:
                restore_sharedir(snap, args.sharedir)
            try:
                run_post_sql(args.dsn, fx)
            except Exception as e:  # noqa: BLE001 - never hide the log
                print("           warning: post_sql failed: %s" % e)
        log_path = os.path.join(results_dir, fid + ".log")
        open(log_path, "w", encoding="utf-8").write(out)

        actual, totals = parse_failures(out)
        sep = fx.get("failure_detail_sep")
        if sep:
            # A suite without a per-name summary prints the detail on the
            # inline line (test_perf_envelope.py: "name -- vanilla ..., ...
            # накладные 3201.4 мкс"). The suffix is measurement-dependent, so
            # compare the assertion name only. Opt-in per fixture.
            actual = [n.split(sep, 1)[0] for n in actual]
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
