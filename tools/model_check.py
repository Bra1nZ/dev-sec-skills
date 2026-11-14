#!/usr/bin/env python3
"""Step 5: check the model against the code and against itself.

Five checks, and a status that is derived from them rather than written by hand:

* ``anchor``   — every anchored primitive still hashes to the same snippet;
  an anchor without a hash is ``unanchored`` (it was never valid), distinct
  from ``stale`` (the file changed);
* ``coverage`` — every required operation is decided, and every ``&mut self``
  operation is either guarded or explicitly ``no_guard_ok``. Test code is
  skipped by default (``--include-tests`` checks it as well), and a private
  read-only operation without a decision is counted as not required;
* ``vacuity``  — a guard that can never hold (``false``, ``x == 1 && x == 2``)
  makes every proof about it empty. One exception, counted separately as
  ``fail_loud_excluded``: ``debug_assert!(false, ...)`` is an intentional
  fail-loud marker for an unreachable arm, not a silently dead guard;
* ``dead_state`` — a field nobody reads or nobody writes;
* ``theorem``  — an invariant that is a tautology, or one whose scope touches
  none of the state it names. An ``assert!`` invariant follows its operation:
  approving the operation approves the assert.

V0 never emits ``model-checked``. Bounds can be declared, and are recorded, but
there is no bounded enumerator behind them yet; claiming ``model-checked`` from
a declared file alone would be exactly the dishonesty the ladder forbids.

The environment scope is mandatory (``--environment offline | ci |
full-local``): an environment-dependent failure is an artifact, not a PR bug,
only with a recorded scope. A failure without one cannot be classified, and
"fails in my offline build" and "fails in CI" are different findings.

Exit codes: 0 all mandatory checks pass, 1 a mandatory check failed, 2 usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from model_primitives import (
    FORMAT_CHECKS, ModelError, add_target_args, anchor_state, bounds_of,
    decision_map, journal_crash, load_decisions, load_primitives, now_iso,
    prepare, sha256_file, tool_block, write_json,
)


def invariant_decided(invariant, chosen, op_decision) -> bool:
    """An assert invariant follows its operation (group decision).

    ``decided_by`` is the operation: approving the operation approves the
    assert it carries. A doc invariant is decided on its own.
    """
    own = (chosen.get(invariant["id"]) or {}).get("decision")
    if own == "approved":
        return True
    if invariant.get("kind") == "assert":
        return op_decision == "approved"
    return False


def walk_anchors(node, label=""):
    """Yield ``(label, anchor)`` for every anchor in the primitives tree."""
    if isinstance(node, dict):
        if {"path", "start", "end"} <= set(node) and "sha256" in node:
            yield label, node
            return
        for key, value in node.items():
            if key in ("guards", "effects", "invariants", "entities", "state",
                       "operations", "unmapped"):
                yield from walk_anchors(value, key)
            elif isinstance(value, (dict, list)):
                yield from walk_anchors(value, key)
    elif isinstance(node, list):
        for entry in node:
            yield from walk_anchors(entry, label)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_tautology(text: str) -> bool:
    value = normalise(text).strip(" ;")
    if value in ("true", "1 == 1", "0 == 0"):
        return True
    match = re.fullmatch(r"([A-Za-z_][\w.]*)\s*==\s*\1", value)
    return bool(match)


def contradictory(text: str):
    """Very small contradiction detector: ``x == a && x == b``, a != b."""
    value = normalise(text)
    parts = [part.strip() for part in value.split("&&")]
    if len(parts) < 2:
        return None
    equalities = []
    for part in parts:
        match = re.fullmatch(r"([A-Za-z_][\w.]*)\s*==\s*([A-Za-z_0-9.]+)", part)
        if match:
            equalities.append((match.group(1), match.group(2)))
    for i, (left, a) in enumerate(equalities):
        for right, b in equalities[i + 1:]:
            if left == right and a != b:
                return "`%s` cannot be both `%s` and `%s`" % (left, a, b)
    return None


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Check anchors, coverage, vacuity and dead state.")
    add_target_args(ap)
    ap.add_argument("--include-tests", action="store_true",
                    help="check test code as well (excluded by default)")
    # An environment-dependent failure is an artifact, not a PR bug, only
    # with a recorded scope: "fails in my offline build without X" and "fails
    # in CI" are different findings. A run without the scope cannot be
    # classified, so the argument is mandatory.
    ap.add_argument("--environment", required=True,
                    choices=("offline", "ci", "full-local"),
                    help="environment scope of this run (mandatory)")
    args = ap.parse_args(argv)
    started = time.time()

    info, out, console, journal = prepare(args, "check")
    try:
        primitives = load_primitives(out)
        decisions = load_decisions(out)
        chosen = decision_map(decisions)
        bounds = bounds_of(out)
        root = (primitives.get("target") or {}).get("path") or info["path"]

        checks = []
        counts = {"anchors": 0, "stale": 0, "missing": 0, "unanchored": 0,
                  "undecided": 0, "unguarded_mut_self": 0, "vacuity_hits": 0,
                  "fail_loud_excluded": 0,
                  "dead_state": 0, "tautologies": 0, "not_required": 0,
                  "test_skipped": 0}

        # -- anchors ------------------------------------------------------
        stale = []
        for label, anchor in walk_anchors(primitives):
            counts["anchors"] += 1
            state, detail = anchor_state(anchor, root)
            if state == "stale":
                counts["stale"] += 1
                stale.append("%s: %s:%s-%s (%s)"
                             % (label, anchor["path"], anchor["start"],
                                anchor["end"], detail))
            elif state == "missing":
                counts["missing"] += 1
                stale.append("%s: %s (%s)" % (label, anchor.get("path"),
                                              detail))
            elif state == "unanchored":
                counts["unanchored"] += 1
                stale.append("%s: %s:%s-%s (%s)"
                             % (label, anchor["path"], anchor["start"],
                                anchor["end"], detail))
        checks.append({
            "id": "anchor",
            "status": "fail" if stale else "pass",
            "detail": "%d anchors, %d stale, %d missing, %d unanchored"
                      % (counts["anchors"], counts["stale"], counts["missing"],
                         counts["unanchored"]),
            "items": stale[:100],
        })

        # -- coverage -----------------------------------------------------
        problems = []
        approved_ops = []
        for op in primitives.get("operations") or []:
            if op.get("test") and not args.include_tests:
                counts["test_skipped"] += 1
                continue
            entry = chosen.get(op["id"]) or {}
            decision = entry.get("decision")
            if not op.get("required", True) and decision not in (
                    "approved", "rejected", "deferred"):
                # A private read-only operation without effects is answered by
                # its callers; it does not require its own decision.
                counts["not_required"] += 1
                continue
            if decision not in ("approved", "rejected", "deferred"):
                counts["undecided"] += 1
                if op.get("visibility") == "public" or op.get("mut_self"):
                    problems.append("%s `%s`: no decision (public entry point)"
                                    % (op["id"], op["name"]))
                continue
            if decision != "approved":
                continue
            approved_ops.append(op)
            if op.get("mut_self") and not op.get("guards"):
                counts["unguarded_mut_self"] += 1
                if not entry.get("no_guard_ok"):
                    problems.append(
                        "%s `%s`: &mut self without a guard and without "
                        "no_guard_ok" % (op["id"], op["name"]))
                elif not entry.get("note"):
                    problems.append(
                        "%s `%s`: no_guard_ok without a note naming the "
                        "enforcement point" % (op["id"], op["name"]))
        checks.append({
            "id": "coverage",
            "status": "fail" if problems else "pass",
            "detail": "%d approved operations, %d undecided, %d unguarded "
                      "&mut self, %d not required, %d test skipped"
                      % (len(approved_ops), counts["undecided"],
                         counts["unguarded_mut_self"], counts["not_required"],
                         counts["test_skipped"]),
            "items": problems[:100],
        })

        # -- vacuity ------------------------------------------------------
        # A guard that can never hold is vacuous. One exception, counted
        # separately: debug_assert!(false, ...) is an intentional fail-loud
        # marker for an unreachable arm (it fires in debug builds and is
        # compiled out in release), not a silently dead guard. The five
        # "vacuous" hits in craft-libs (Iteration 6) were all of this kind.
        vacuous = []
        for op in primitives.get("operations") or []:
            if op.get("test") and not args.include_tests:
                continue
            decision = (chosen.get(op["id"]) or {}).get("decision")
            approved = decision == "approved"
            for guard in op.get("guards") or []:
                text = normalise(guard.get("condition"))
                reason = None
                if text in ("false", "!true"):
                    if str(guard.get("macro") or "").startswith("debug_assert"):
                        counts["fail_loud_excluded"] += 1
                    else:
                        reason = "condition is literally false"
                elif contradictory(text):
                    reason = contradictory(text)
                if reason:
                    counts["vacuity_hits"] += 1
                    vacuous.append("%s `%s`%s: %s"
                                   % (op["id"], op["name"],
                                      "" if approved else " (not approved)",
                                      reason))
        checks.append({
            "id": "vacuity",
            "status": "fail" if vacuous else "pass",
            "detail": "%d hit(s)%s" % (len(vacuous),
                                       ", %d fail-loud excluded"
                                       % counts["fail_loud_excluded"]
                                       if counts["fail_loud_excluded"] else ""),
            "items": vacuous[:100],
        })

        # -- dead state ---------------------------------------------------
        dead = []
        for state in primitives.get("state") or []:
            if state.get("test") and not args.include_tests:
                continue
            if (chosen.get(state["id"]) or {}).get("decision") != "approved":
                continue
            readers = state.get("read_by") or []
            writers = state.get("written_by") or []
            if not readers:
                counts["dead_state"] += 1
                dead.append("%s `%s.%s`: never read" % (state["id"],
                                                        state.get("entity"),
                                                        state.get("field")))
            if not writers:
                counts["dead_state"] += 1
                dead.append("%s `%s.%s`: never written" % (state["id"],
                                                           state.get("entity"),
                                                           state.get("field")))
        checks.append({
            "id": "dead_state",
            "status": "warn" if dead else "pass",
            "detail": "%d finding(s)" % len(dead),
            "items": dead[:100],
        })

        # -- theorem sanity ----------------------------------------------
        weak = []
        fields_by_op = {}
        op_decision = {}
        for op in primitives.get("operations") or []:
            fields_by_op[op["id"]] = {
                effect["target"].replace("self.", "")
                for effect in op.get("effects") or []
            }
            op_decision[op["id"]] = (chosen.get(op["id"]) or {}).get("decision")
        for invariant in primitives.get("invariants") or []:
            if invariant.get("test") and not args.include_tests:
                continue
            if not invariant_decided(invariant, chosen,
                                     op_decision.get(invariant.get("scope"))):
                continue
            text = invariant.get("text") or ""
            if is_tautology(text):
                counts["tautologies"] += 1
                weak.append("%s: tautology `%s`" % (invariant["id"],
                                                    normalise(text)))
                continue
            scope = invariant.get("scope")
            touched = fields_by_op.get(scope)
            if touched is not None:
                named = {name for name in re.findall(r"[A-Za-z_]\w*", text)
                         if name in touched}
                if touched and not named:
                    weak.append("%s: scope `%s` touches none of the fields the "
                                "invariant names" % (invariant["id"], scope))
        checks.append({
            "id": "theorem",
            "status": "fail" if any("tautology" in item for item in weak)
                      else ("warn" if weak else "pass"),
            "detail": "%d tautolog%s, %d weak scope(s)"
                      % (counts["tautologies"],
                         "y" if counts["tautologies"] == 1 else "ies",
                         len(weak) - counts["tautologies"]),
            "items": weak[:100],
        })

        failures = [check for check in checks if check["status"] == "fail"]
        status = "tested" if not failures and approved_ops else "open"
        limitations = [
            "V0 derives guards, effects and candidate invariants; it does not "
            "derive security goals.",
            "V0 has no bounded state enumerator, so it never claims "
            "model-checked, even when bounds.yaml is present.",
            "Event-B consistency is not checked here; model.sys is a skeleton.",
        ]
        if bounds:
            limitations.append(
                "bounds.yaml is present and recorded, but nothing enumerated "
                "the domain behind it in this run.")

        payload = {
            "format": FORMAT_CHECKS,
            "generated": now_iso(),
            "tool": tool_block("model_check"),
            "target": primitives.get("target"),
            "status": status,
            "environment": args.environment,
            "checks": checks,
            "counts": counts,
            "bounds": {
                "declared": bool(bounds),
                "values": (bounds or {}).get("bounds"),
                "enumerated": False,
            },
            "limitations": limitations,
        }
        path = os.path.join(out, "checks", "results.json")
        write_json(path, payload)

        console("check: %d anchors, %d stale, %d missing"
                % (counts["anchors"], counts["stale"], counts["missing"]))
        for check in checks:
            console("  %-11s %-5s %s" % (check["id"], check["status"],
                                         check["detail"]))
            for item in check["items"][:10]:
                console("      %s" % item)
        console("  status      %s" % status)
        console("  environment %s" % args.environment)

        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0 if status == "tested" else 1,
            duration_ms=int((time.time() - started) * 1000),
            inputs=[{"path": os.path.join(out, "primitives.yaml"),
                     "sha256": sha256_file(os.path.join(out, "primitives.yaml"))}],
            outputs=[{"path": path, "sha256": sha256_file(path)}],
            counts=counts, status=status, environment=args.environment,
        )
        print("check: %s (%d stale, %d undecided, %d unguarded, %d vacuous)"
              % (status, counts["stale"], counts["undecided"],
                 counts["unguarded_mut_self"], counts["vacuity_hits"]))
        return 0 if status == "tested" else 1
    except ModelError as exc:
        console("check: %s" % exc)
        journal.write(argv=sys.argv[1:], target=info["path"],
                      target_commit=info["commit"], dirty=info["dirty"],
                      exit_code=2,
                      duration_ms=int((time.time() - started) * 1000),
                      status="error", error=str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001 - a crash must still be journaled
        journal_crash(console, journal, exc, started, argv=sys.argv[1:],
                      target=info["path"], target_commit=info["commit"],
                      dirty=info["dirty"])
        return 2
    finally:
        console.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
