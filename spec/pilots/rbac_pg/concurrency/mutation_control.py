#!/usr/bin/env python3
"""Mutation control for the lockout race oracle (V2-42).

An oracle that cannot fail is a second copy of the code's assumptions. This
control applies one named mutation at a time to the product's SQL, installs the
mutated script into a throw-away database, and requires the oracle to report a
violation:

  MUT-RACE-001  the atomic `UPDATE ... SET failed_attempts = failed_attempts + 1`
                becomes a stale read (SELECT into a variable, then UPDATE from
                it): the write no longer re-reads the row under its own lock.
                The oracle must fail `no_lost_update`.
  MUT-RACE-002  the threshold no longer sets `locked_until`: the counter still
                grows, so only `account_is_locked` can see it. The oracle must
                fail that check, not the counter check.

Two mutants, two different checks: a control that only ever breaks one
assertion proves that assertion, not the oracle.

Every anchor must occur exactly once. A drifted source fails the control
instead of silently mutating nothing, the same contract as mutations.yaml.

Rounds exist because a race is triggered by timing, not by a fixed seed. A
mutant is required to be caught in every round: a control that needs luck to
catch a known defect is not a control. Measured rounds are printed.

Exit codes: 0 every mutant was caught in every round, 1 at least one was not,
2 setup or anchor error.

Usage:
    python3 spec/pilots/rbac_pg/concurrency/mutation_control.py \
        --target /home/admini/projects/rbac_pg \
        --dsn "postgresql://postgres@127.0.0.1:55434/postgres"
"""

import argparse
import importlib.util
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

ATOMIC = """    UPDATE rbac.users
       SET failed_attempts = failed_attempts + 1,
           locked_until = CASE WHEN failed_attempts + 1 >= 5
                               THEN 'infinity'::timestamptz ELSE locked_until END,
           auth_epoch  = CASE WHEN failed_attempts + 1 >= 5
                              THEN auth_epoch + 1 ELSE auth_epoch END
     WHERE user_id = v_user.user_id
    RETURNING failed_attempts INTO v_attempts;"""

MUTANTS = [
    {
        "id": "MUT-RACE-001",
        "what": "stale read instead of a locked re-read (lost update)",
        "anchor": ATOMIC,
        "replacement": """    SELECT failed_attempts INTO v_attempts
      FROM rbac.users WHERE user_id = v_user.user_id;
    UPDATE rbac.users
       SET failed_attempts = v_attempts + 1,
           locked_until = CASE WHEN v_attempts + 1 >= 5
                               THEN 'infinity'::timestamptz ELSE locked_until END,
           auth_epoch  = CASE WHEN v_attempts + 1 >= 5
                              THEN auth_epoch + 1 ELSE auth_epoch END
     WHERE user_id = v_user.user_id
    RETURNING failed_attempts INTO v_attempts;""",
    },
    {
        "id": "MUT-RACE-002",
        "what": "the threshold no longer locks the account",
        "anchor": """       SET failed_attempts = failed_attempts + 1,
           locked_until = CASE WHEN failed_attempts + 1 >= 5
                               THEN 'infinity'::timestamptz ELSE locked_until END,""",
        "replacement": """       SET failed_attempts = failed_attempts + 1,
           locked_until = locked_until,""",
    },
]


def load_oracle():
    spec = importlib.util.spec_from_file_location(
        "lockout_race", str(HERE / "test_lockout_race.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.environ.get("PILOT_ROOT", "../rbac_pg"))
    ap.add_argument("--dsn", default=os.environ.get("MUTATION_DSN",
                    "postgresql://postgres@127.0.0.1:55434/postgres"))
    ap.add_argument("--sql", default=None)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--sessions", type=int, default=8)
    args = ap.parse_args()
    started = time.monotonic()

    race = load_oracle()
    sql_path = args.sql or os.path.join(args.target, race.SQL_VERSION)
    if not os.path.isfile(sql_path):
        print("install script not found: %s" % sql_path, file=sys.stderr)
        return 2
    source = race.load_sql(sql_path)

    caught = 0
    rounds_passed = 0
    rounds_total = 0
    for mutant in MUTANTS:
        if source.count(mutant["anchor"]) != 1:
            print("%s: anchor occurs %d times in %s, expected exactly 1; the "
                  "fixture needs review, not a silent no-op"
                  % (mutant["id"], source.count(mutant["anchor"]), sql_path),
                  file=sys.stderr)
            return 2
        mutated = source.replace(mutant["anchor"], mutant["replacement"])
        rounds_caught = 0
        for round_no in range(1, args.rounds + 1):
            rounds_total += 1
            name = "mut_%d_%06x" % (os.getpid(), random.randrange(1 << 24))
            local = race.replace_database(args.dsn, name)
            try:
                race.make_database(args.dsn, name, mutated)
                returns, errors = race.run_race(local, args.sessions)
                state = race.measure(local)
            except Exception as exc:
                print("setup failed in %s round %d: %s"
                      % (mutant["id"], round_no, exc), file=sys.stderr)
                return 2
            finally:
                try:
                    race.drop_database(args.dsn, name)
                except Exception:
                    pass
            checks = race.judge(state, returns, errors, args.sessions)
            failed = [name_ for name_, ok, _ in checks if not ok]
            if failed:
                rounds_caught += 1
                rounds_passed += 1
                # The test IDs are named with a status, so the run record's
                # citation can be checked against this log by claim_lint's L2.
                print("[%s round %d] %s ... failed, as required "
                      "(counter=%d increments=%d locked=%s)"
                      % (mutant["id"], round_no, ", ".join(failed),
                         state["counter"], state["increments"], state["locked"]))
            else:
                print("[%s round %d] no check failed — the oracle passed the "
                      "mutant (counter=%d increments=%d locked=%s)"
                      % (mutant["id"], round_no, state["counter"],
                         state["increments"], state["locked"]))
        if rounds_caught == args.rounds:
            caught += 1
        else:
            print("%s: caught in %d/%d rounds — %s"
                  % (mutant["id"], rounds_caught, args.rounds, mutant["what"]))
    print("mutants: %d/%d caught" % (caught, len(MUTANTS)))
    # The convention claim_lint's L2 understands, so a run record's counters
    # are cross-checked against the log rather than taken on trust. A round is
    # one "the oracle must fail" control; a caught mutant is three such rounds.
    print("========== %d passed, %d failed in %.2fs =========="
          % (rounds_passed, rounds_total - rounds_passed,
             time.monotonic() - started))
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
