#!/usr/bin/env python3
"""Prove that evals/proof-plan/run_evals.py can fail (V2-29).

A green eval suite is evidence only if a broken planner turns it red. This
harness applies eight named mutations to tools/proof_plan.py, runs the full
scenario set against each mutant, and requires that the scenario which names
the mutated behaviour is among the failures. A mutation that is not caught is
reported as a gap in the suite, not as a planner bug.

The mutations are textual: if tools/proof_plan.py is refactored, an anchor
stops matching and the harness exits 2 instead of silently testing nothing.

Usage:
    python3 evals/proof-plan/mutation_selftest.py [--only NAME]
"""

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import run_evals as E  # noqa: E402

REPO = E.REPO

# name -> (anchor in the tool, replacement, scenario that must go red)
MUTANTS = [
    (
        "freshness-strict",
        "record_finished >= datetime.fromtimestamp(last, timezone.utc)",
        "record_finished > datetime.fromtimestamp(last, timezone.utc)",
        "record-timestamp-equal-is-fresh",
    ),
    (
        "ignore-old-path-material",
        '        if item.get("old_path"):\n'
        '            paths.append(item["old_path"].lstrip("./"))',
        "        pass",
        "renamed-proof-material-reports-gap",
    ),
    (
        "status-gate-inside-reasons",
        '''        elif record_status != "completed":
            # A record that did not complete proves nothing, whether or not the
            # diff touched a dependency. Checked before the reasons gate on
            # purpose: `unverified`/`failed`/missing status never becomes fresh.
            status = "rerun"
            reasons.append({"kind": "record-not-completed",
                            "path": entry["tool_output"]})
        elif reasons:
            only_manifest = all(r["kind"] in ("manifest-changed", "proof-added")
                                for r in reasons)
            if only_manifest:''',
        '''        elif reasons:
            only_manifest = all(r["kind"] in ("manifest-changed", "proof-added")
                                for r in reasons)
            if record_status != "completed":
                status = "rerun"
                reasons.append({"kind": "record-not-completed",
                                "path": entry["tool_output"]})
            elif only_manifest:''',
        "failed-record-no-change-reruns",
    ),
    (
        "manifest-change-is-fresh",
        "            if only_manifest:\n"
        "                # The proof definition itself moved; the old record describes\n"
        "                # the old definition, so it cannot cover the new one.\n"
        '                status = "rerun"',
        "            if False:\n"
        '                status = "rerun"',
        "manifest-changed-reruns",
    ),
    (
        "match-ignores-rename",
        '        if regex.match(item["path"].lstrip("./")) or \\\n'
        '                (item.get("old_path") and\n'
        '                 regex.match(item["old_path"].lstrip("./"))):',
        '        if regex.match(item["path"].lstrip("./")):',
        "renamed-dependency-stale",
    ),
    (
        "complete-gate-noop",
        '    if args.require_complete and result["summary"]["unmapped"]:',
        '    if False and result["summary"]["unmapped"]:',
        "require-complete-blocks-unmapped",
    ),
    (
        "all-is-fresh",
        '        if args.all:\n            status = "rerun"',
        '        if args.all:\n            status = "fresh"',
        "all-forces-rerun",
    ),
    (
        "unknown-key-ignored",
        '        unknown = set(entry) - allowed\n        if unknown:',
        '        unknown = set(entry) - allowed\n        if False:',
        "unknown-entry-key-rejected",
    ),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default=None, help="run one named mutation")
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "proof_plan.py"))
    args = ap.parse_args()

    source = open(args.tool, encoding="utf-8").read()
    if args.only:
        selected = [m for m in MUTANTS if m[0] == args.only]
        if not selected:
            print("error: unknown mutation %s" % args.only, file=sys.stderr)
            return 2
    else:
        selected = MUTANTS

    td = tempfile.mkdtemp(prefix="proof-plan-mutants-")
    caught = 0
    try:
        for name, anchor, replacement, must_fail in selected:
            if anchor not in source:
                print("error: anchor for %s is gone; update the harness"
                      % name, file=sys.stderr)
                return 2
            path = os.path.join(td, name + ".py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(source.replace(anchor, replacement, 1))
            failed = []
            for scenario in E.SCENARIOS:
                _, problems = E.run(scenario, path)
                if problems:
                    failed.append(scenario["name"])
            if must_fail in failed:
                caught += 1
                print("caught %-28s by %d case(s), incl. %s"
                      % (name, len(failed), must_fail))
            else:
                print("MISSED %-28s %d case(s) failed, none named %s: %s"
                      % (name, len(failed), must_fail, ", ".join(failed) or "-"))
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print("%d/%d mutations were caught by a case named for the behaviour"
          % (caught, len(selected)))
    return 0 if caught == len(selected) else 1


if __name__ == "__main__":
    sys.exit(main())
