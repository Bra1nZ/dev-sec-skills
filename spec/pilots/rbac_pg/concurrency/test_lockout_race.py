#!/usr/bin/env python3
"""Concurrency oracle for INV-TX-003 on rbac_pg's lockout path (V2-42).

`rbac.register_auth_failure()` is a check-then-act sequence: it reads
`locked_until` into a record, decides "not locked", and only then increments
`failed_attempts` in an UPDATE. The invariant this oracle checks is the one the
catalogue states for that shape: concurrent writers never lose an increment,
and the threshold is enforced by the write, not by the check.

The oracle does not assert a fixed final counter. How many sessions reach the
incrementing branch depends on scheduling: a session that starts after the
lock committed takes the "already locked" branch and does not increment. The
scheduling-independent form is an identity:

    failed_attempts == start_attempts + (increments the product itself logged)

The incrementing branch writes an AUTH_FAILURE event without a `reason` field;
the "already locked" branch writes `reason = account_already_locked`. The
event table is the product's own account of what it did, so the oracle asks
the product to be consistent with its own log rather than with the oracle's
idea of a schedule.

What it does NOT say:
  * It is one path (lockout), one PostgreSQL version, one machine. It is a
    reference implementation of the INV-TX-003 oracle shape, not proof that
    the invariant holds for grants, policy application or RLS.
  * It does not measure latency, deadlocks or lock waits; a run that takes
    minutes still passes.
  * It installs the catalogue's SQL as a plain script (`CREATE EXTENSION` is
    skipped, so `extversion` bookkeeping does not exist in the test database).
    A defect that depends on the extension packaging is invisible here.
  * The mutations are named and written by hand; a caught mutant says the
    oracle is sensitive to those edits, not that it covers every race.

Every run creates a throw-away database and drops it on exit unless --keep.

Exit codes: 0 the oracle passed, 1 a violation, 2 setup error.

Usage:
    python3 spec/pilots/rbac_pg/concurrency/test_lockout_race.py \
        --target /home/admini/projects/rbac_pg \
        --dsn "postgresql://postgres@127.0.0.1:55434/postgres"
"""

import argparse
import os
import random
import sys
import threading
import time

try:
    import psycopg2  # type: ignore
except ImportError:  # pragma: no cover
    sys.exit("psycopg2 is required: pip install psycopg2-binary")

DEFAULT_DSN = "postgresql://postgres@127.0.0.1:55434/postgres"
SQL_VERSION = "sql/rbac--1.9.1.sql"
THRESHOLD = 5          # rbac_pg v1.9 B2: five failed authentications lock the account
START_ATTEMPTS = 4     # one short of the threshold, so the race is at the edge
SESSIONS = 8


def load_sql(path):
    """Read the install script and strip psql meta-commands.

    The first line is a `\\echo ... \\quit` guard that makes a sourced script
    stop; executing the script through a driver must drop it.
    """
    text = open(path, encoding="utf-8").read()
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("\\"))


def make_database(local_dsn, name, sql_text):
    """Create a throw-away database and install the catalogue SQL into it."""
    import psycopg2
    admin = psycopg2.connect(local_dsn)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute('DROP DATABASE IF EXISTS "%s"' % name)
    cur.execute('CREATE DATABASE "%s"' % name)
    conn = psycopg2.connect(replace_database(local_dsn, name))
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        cur.execute("CREATE SCHEMA IF NOT EXISTS rbac")
        cur.execute(sql_text)
        cur.execute("INSERT INTO rbac.users (username) VALUES ('race-victim')")
        cur.execute("UPDATE rbac.users SET failed_attempts = %s "
                    "WHERE username = 'race-victim'", (START_ATTEMPTS,))
        return True
    finally:
        conn.close()
        admin.close()


def drop_database(local_dsn, name):
    import psycopg2
    admin = psycopg2.connect(local_dsn)
    admin.autocommit = True
    try:
        admin.cursor().execute('DROP DATABASE IF EXISTS "%s"' % name)
    finally:
        admin.close()


def replace_database(dsn, name):
    """Swap the database component of a libpq URL or key=value DSN."""
    if dsn.startswith(("postgresql://", "postgres://")):
        head, _, _ = dsn.rpartition("/")
        return "%s/%s" % (head, name)
    parts = [p for p in dsn.split() if not p.startswith("dbname=")]
    parts.append("dbname=%s" % name)
    return " ".join(parts)


def run_race(local_dsn, sessions):
    """Fire `sessions` concurrent register_auth_failure calls at one account.

    Every worker has its own connection and waits on a barrier, so the check
    in each transaction happens before any of them commits the write. Returns
    the returned counters and the exceptions, in start order.
    """
    import psycopg2
    barrier = threading.Barrier(sessions)
    results = []
    errors = []
    lock = threading.Lock()

    def worker(index):
        conn = psycopg2.connect(local_dsn)
        conn.autocommit = True
        try:
            cur = conn.cursor()
            barrier.wait()
            cur.execute("SELECT rbac.register_auth_failure('race-victim')")
            value = cur.fetchone()[0]
        except Exception as exc:  # recorded, then judged by the oracle
            with lock:
                errors.append("session %d: %s" % (index, str(exc).splitlines()[0]))
            return
        finally:
            conn.close()
        with lock:
            results.append((index, value))

    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(sessions)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(results), errors


def measure(local_dsn):
    """Read the state the product is in after the race."""
    import psycopg2
    conn = psycopg2.connect(local_dsn)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT failed_attempts, locked_until IS NOT NULL, auth_epoch, "
                    "locked_until FROM rbac.users WHERE username = 'race-victim'")
        counter, locked, epoch, locked_until = cur.fetchone()
        cur.execute("SELECT count(*) FROM rbac.security_events "
                    "WHERE event_type = 'AUTH_FAILURE' "
                    "AND details ->> 'username' = 'race-victim' "
                    "AND NOT (details ? 'reason')")
        increments = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM rbac.security_events "
                    "WHERE event_type = 'AUTH_FAILURE' "
                    "AND details ->> 'username' = 'race-victim' "
                    "AND details ->> 'reason' = 'account_already_locked'")
        already_locked = cur.fetchone()[0]
        return {"counter": counter, "locked": locked, "locked_until": locked_until,
                "epoch": epoch, "increments": increments,
                "already_locked": already_locked}
    finally:
        conn.close()


def test_account_is_locked(state, returns, errors, sessions):
    """The threshold is enforced by the write, not only by the check."""
    return state["locked"], "locked_until=%r" % (state["locked_until"],)


def test_no_lost_update(state, returns, errors, sessions):
    """Every increment the product logged is visible in the counter.

    The identity is scheduling-independent on purpose: a session that starts
    after the lock committed does not increment, and the product records that
    in its own event log.
    """
    expected = START_ATTEMPTS + state["increments"]
    return (state["counter"] == expected,
            "failed_attempts=%d, start=%d + logged increments=%d = %d"
            % (state["counter"], START_ATTEMPTS, state["increments"], expected))


def test_every_session_reported(state, returns, errors, sessions):
    """No session hangs, crashes or is silently dropped."""
    return (not errors and len(returns) + len(errors) == sessions,
            "%d session(s) answered, %d error(s)%s"
            % (len(returns), len(errors),
               (": " + "; ".join(errors[:3])) if errors else ""))


CHECKS = (test_account_is_locked, test_no_lost_update, test_every_session_reported)
__test__ = False  # these take fixtures as arguments; pytest must not collect them


def judge(state, returns, errors, sessions):
    """Run every check and return (name, ok, detail) in a fixed order."""
    return [(fn.__name__, ok, detail)
            for fn in CHECKS
            for ok, detail in (fn(state, returns, errors, sessions),)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.environ.get("PILOT_ROOT", "../rbac_pg"),
                    help="rbac_pg checkout (default: ../rbac_pg)")
    ap.add_argument("--dsn", default=os.environ.get("MUTATION_DSN", DEFAULT_DSN),
                    help="DSN of the maintenance database (default: %s)" % DEFAULT_DSN)
    ap.add_argument("--sql", default=None,
                    help="install script (default: <target>/%s)" % SQL_VERSION)
    ap.add_argument("--sessions", type=int, default=SESSIONS)
    ap.add_argument("--keep", action="store_true",
                    help="keep the throw-away database for inspection")
    args = ap.parse_args()
    started = time.monotonic()

    sql_path = args.sql or os.path.join(args.target, SQL_VERSION)
    if not os.path.isfile(sql_path):
        print("install script not found: %s" % sql_path, file=sys.stderr)
        return 2
    sql_text = load_sql(sql_path)
    name = "race_%d_%06x" % (os.getpid(), random.randrange(1 << 24))
    local = replace_database(args.dsn, name)
    try:
        make_database(args.dsn, name, sql_text)
        results, errors = run_race(local, args.sessions)
        state = measure(local)
    except Exception as exc:
        print("setup failed: %s" % exc, file=sys.stderr)
        return 2
    finally:
        if not args.keep:
            try:
                drop_database(args.dsn, name)
            except Exception:
                pass

    checks = judge(state, results, errors, args.sessions)
    print("measured: counter=%d locked=%s increments=%d already_locked=%d "
          "epoch=%d sessions=%d"
          % (state["counter"], state["locked"], state["increments"],
             state["already_locked"], state["epoch"], args.sessions))
    print("returns: %s" % ", ".join(str(v) for _, v in results))
    failed = 0
    for name_, ok, detail in checks:
        # "name ... ok|failed" is the shape claim_lint's L2 recognizes when it
        # checks that every cited test ID was actually executed in this log.
        print("%s ... %s — %s" % (name_, "ok" if ok else "failed", detail))
        failed += 0 if ok else 1
    print("ИТОГ: %d OK, %d FAIL" % (len(checks) - failed, failed))
    # A conventional summary line, so a run record's tests_run/tests_passed can
    # be cross-checked against the log by tools/claim_lint.py instead of being
    # taken on trust. The counts are the oracle's three checks.
    print("========== %d passed, %d failed in %.2fs =========="
          % (len(checks) - failed, failed, time.monotonic() - started))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
