#!/usr/bin/env python3
"""Step 3: put the extracted primitives in front of a human.

`review` writes the decision queue and never decides anything itself:

* ``decisions.yaml`` — one entry per *required* primitive with ``decision:
  null``. The human fills in ``approved`` / ``rejected`` / ``deferred``.
  Entries already present are preserved, so re-running after new code is safe.
* ``review.md`` — the summary, the known verification traps, and the
  risk-ordered decision queue;
* ``review/<area>.md`` — per-area detail: every required operation and the
  assert invariants that follow it;
* ``review-index.json`` — every required primitive: id, path, line, tier,
  plus the trap ids this run carries.

What requires a decision (the required set): entities, state, operations that
are public or ``&mut self``, and doc invariants. What does not: test code
(excluded by default; ``--include-tests`` puts it back), operations that are
private, read-only and effect-free (their callers answer for them), and assert
invariants (they follow their operation; approving the operation approves the
assert, recorded as a group decision). The first real run produced 59,046
entries and a 295k-line checklist; its required set was ~10,500. A queue
nobody can finish is a queue nobody starts.

Risk tiers, most urgent first:

1. ``&mut self`` without a guard — the write is unchecked;
2. public without a guard — an unchecked entry point;
3. everything else.

Exit codes: 0 ok, 2 usage, input or environment error.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import yaml

from model_primitives import (
    DECISIONS, FORMAT_DECISIONS, ModelError, add_target_args, decision_map,
    dump_yaml, journal_crash, load_decisions, load_primitives, now_iso,
    prepare, sha256_file, write_json,
)

TOP_N = 200

# Shipped with the conveyor; review carries the traps into every review.md,
# so a partial copy without them is an environment error, not a soft skip.
DEFAULT_TRAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             os.pardir, "spec", "traps.yaml")


def load_traps(path: str) -> dict:
    """The known-traps file: mistakes that already cost a real run once."""
    if not os.path.isfile(path):
        raise ModelError("traps file not found: %s (shipped as spec/traps.yaml)"
                         % path)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    traps = data.get("traps") or []
    for trap in traps:
        if not (trap.get("id") and trap.get("title") and trap.get("rules")):
            raise ModelError("trap without id, title or rules: %r" % trap)
    data["traps"] = traps
    return data


def _where(anchor) -> str:
    if not anchor:
        return "—"
    digest = (anchor.get("sha256") or "")[:8]
    return "`%s:%s-%s`%s" % (anchor.get("path"), anchor.get("start"),
                             anchor.get("end"),
                             (" " + digest) if digest else "")


def _guard_text(guard) -> str:
    mode = "reject when true" if guard["reject_when"] == "true" \
        else "reject when false"
    return "`%s` (%s)" % (guard["condition"], mode)


def _effect_text(effect) -> str:
    if effect["kind"] == "method":
        return "`%s.%s(%s)`" % (effect["target"], effect.get("method", ""),
                                effect.get("value", ""))
    if effect["kind"] == "init":
        return "`%s := %s` (init)" % (effect["target"], effect.get("value", ""))
    op = effect.get("operator", "=")
    return "`%s %s %s`" % (effect["target"], op, effect.get("value", ""))


def tier(operation) -> int:
    """1 unchecked write, 2 unchecked entry point, 3 otherwise."""
    if operation.get("mut_self") and not operation.get("guards"):
        return 1
    if operation.get("visibility") == "public" and not operation.get("guards"):
        return 2
    return 3


TIER_NAMES = {
    1: "&mut self without a guard — the write is unchecked",
    2: "public without a guard — an unchecked entry point",
    3: "guarded or read-only",
}

TIER_SHELL = {
    1: "mut-self-unguarded",
    2: "public-unguarded",
    3: "guarded",
}


def _area(path: str) -> str:
    parts = (path or "").split("/")
    return "-".join(parts[:2]) if len(parts) > 1 else (parts[0] if parts
                                                       else "other")


def build_review(primitives: dict, decisions: list, chosen: dict,
                 queue: dict, summary: dict, traps: dict,
                 include_tests=False) -> str:
    counts = primitives.get("counts") or {}
    target = primitives.get("target") or {}
    lines = []
    add = lines.append

    add("# Model primitives for review")
    add("")
    add("Target: `%s`  " % target.get("path"))
    add("Commit: `%s`%s  " % (target.get("commit") or "none",
                              " (dirty)" if target.get("dirty") else ""))
    add("Extracted: %s by `model_extract` %s"
        % (primitives.get("generated"),
           (primitives.get("tool") or {}).get("version", "?")))
    add("")
    add("| Primitive | Count |")
    add("| --- | --- |")
    for key in ("entities", "state", "operations", "mut_self_ops", "guards",
                "effects", "invariants", "unmapped"):
        add("| %s | %s |" % (key, counts.get(key, 0)))
    add("")
    add("| Queue | Count |")
    add("| --- | --- |")
    add("| requires a decision | %d |" % summary["required"])
    add("| test code, excluded by default | %d |" % summary["test"])
    add("| private read-only ops, not required | %d |" % summary["not_required"])
    add("| assert invariants following their op | %d |" % summary["asserts"])
    add("")
    add("## How to decide")
    add("")
    add("Edit `decisions.yaml`. Every entry starts with `decision: null`; set it")
    add("to one of `%s`." % "`, `".join(DECISIONS))
    add("")
    add("- `approved` — the primitive enters the generated model;")
    add("- `rejected` — needs a `note` saying what is wrong;")
    add("- `deferred` — needs a `note` saying what is missing.")
    add("")
    add("An operation with `&mut self` and no guard needs either a guard or")
    add("`no_guard_ok: true` with a `note` that names the enforcement point.")
    add("A missing decision is not an approval: it is an open item.")
    add("")
    add("Only the required set asks for decisions. Test code is excluded by")
    add("default (`--include-tests` puts it back); a private, read-only,")
    add("effect-free operation is answered by its callers; an `assert!`")
    add("invariant follows its operation — approving the operation approves")
    add("the assert as a group decision (`decided_by` records it). Decisions")
    add("you already wrote are preserved, including for primitives that left")
    add("the required set.")
    add("")
    add("## Known traps")
    add("")
    add("Verification traps from real runs (%s). A trap is a mistake that"
        % (traps.get("updated") or "JOURNAL.md"))
    add("already cost time once; the rules are the cheapest checks that")
    add("would have caught it. Check them before every test run of the")
    add("target, not after.")
    add("")
    for trap in traps.get("traps") or []:
        add("### %s — %s" % (trap["id"], trap["title"]))
        add("")
        add("Symptom: %s" % trap.get("symptom", ""))
        add("")
        add("Cause: %s" % trap.get("cause", ""))
        add("")
        add("Rules:")
        add("")
        for rule in trap["rules"]:
            add("- %s" % rule)
        add("")
    add("## Decision queue")
    add("")
    add("Ordered by risk. The full lists are in `review/<area>.md` and")
    add("`review-index.json`; below, the %d most urgent per tier." % TOP_N)
    add("")
    breakdown = summary.get("breakdown") or {}
    add("Reconciliation: %d required decisions = %d tiered operations "
        "(tiers below) + %d entities + %d state fields + %d doc invariants."
        % (summary.get("required", 0),
           breakdown.get("tiered_operations", 0),
           breakdown.get("entities", 0), breakdown.get("state", 0),
           breakdown.get("doc_invariants", 0)))
    add("")
    for number in (1, 2, 3):
        operations = queue[number]
        add("### Tier %d — %s" % (number, TIER_NAMES[number]))
        add("")
        add("%d operation(s)." % len(operations))
        add("")
        if operations:
            add("| ID | Name | Signature | Where | Decision |")
            add("| --- | --- | --- | --- | --- |")
            for operation in operations[:TOP_N]:
                entry = chosen.get(operation["id"]) or {}
                add("| `%s` | `%s` | `%s` | %s | %s |"
                    % (operation["id"], operation["name"],
                       operation["signature"],
                       _where(operation.get("anchor")),
                       entry.get("decision") or "*open*"))
            if len(operations) > TOP_N:
                add("")
                add("… and %d more: see `review/` and `review-index.json`."
                    % (len(operations) - TOP_N))
        add("")
    add("## Entities")
    add("")
    add("| ID | Kind | Name | Where | Decision |")
    add("| --- | --- | --- | --- | --- |")
    for entity in primitives.get("entities") or []:
        if entity.get("test") and not include_tests:
            continue
        entry = chosen.get(entity["id"]) or {}
        add("| `%s` | %s | `%s` | %s | %s |"
            % (entity["id"], entity["kind"], entity["name"],
               _where(entity.get("anchor")),
               entry.get("decision") or "*open*"))
    add("")
    for entity in primitives.get("entities") or []:
        if entity.get("test") and not include_tests:
            continue
        if entity.get("variants"):
            names = ", ".join("`%s`" % v["name"] for v in entity["variants"])
            add("- `%s`: variants %s" % (entity["id"], names))
        if entity.get("fields"):
            names = ", ".join("`%s: %s`" % (f["name"], f["type"])
                              for f in entity["fields"])
            add("- `%s`: fields %s" % (entity["id"], names))
    add("")

    add("## State")
    add("")
    add("| ID | Field | Type | Read by | Written by | Where | Decision |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for state in primitives.get("state") or []:
        if state.get("test") and not include_tests:
            continue
        entry = chosen.get(state["id"]) or {}
        add("| `%s` | `%s.%s` | `%s` | %s | %s | %s | %s |"
            % (state["id"], state.get("entity"), state.get("field"),
               state.get("type") or "?",
               ", ".join(state.get("read_by") or []) or "—",
               ", ".join(state.get("written_by") or []) or "—",
               _where(state.get("anchor")),
               entry.get("decision") or "*open*"))
    add("")

    add("## Operations")
    add("")
    add("Required operations carry a decision. The rest are shown without one:")
    add("they are private, read-only and effect-free, and their callers answer")
    add("for them. Per-area detail: `review/<area>.md`.")
    add("")
    add("| ID | Name | Tier | Flags | Where | Decision |")
    add("| --- | --- | --- | --- | --- | --- |")
    for operation in primitives.get("operations") or []:
        if operation.get("test") and not include_tests:
            continue
        entry = chosen.get(operation["id"]) or {}
        required = operation.get("required", True)
        flags = []
        if operation.get("mut_self"):
            flags.append("`&mut self`")
        flags.append("%d guard(s)" % len(operation.get("guards") or []))
        if not required:
            flags.append("not required (private, read-only)")
        add("| `%s` | `%s` | %s | %s | %s | %s |"
            % (operation["id"], operation["name"], tier(operation),
               ", ".join(flags),
               _where(operation.get("anchor")),
               (entry.get("decision") or "*open*") if required
               else "not required"))
    add("")

    add("## Candidate invariants (doc)")
    add("")
    add("| ID | Scope | Text | Where | Decision |")
    add("| --- | --- | --- | --- | --- |")
    for invariant in primitives.get("invariants") or []:
        if invariant.get("kind") != "doc":
            continue
        if invariant.get("test") and not include_tests:
            continue
        entry = chosen.get(invariant["id"]) or {}
        add("| `%s` | `%s` | %s | %s | %s |"
            % (invariant["id"], invariant.get("scope") or "—",
               invariant["text"].replace("|", "\\|"),
               _where(invariant.get("anchor")),
               entry.get("decision") or "*open*"))
    add("")
    add("A candidate invariant is a hypothesis. Approving it says the sentence")
    add("is worth proving, not that the code enforces it. `assert!` invariants")
    add("are not listed here: they follow their operation (see `review/`).")
    add("")

    add("## Unmapped")
    add("")
    add("These are not primitives: they are places where the extractor refused")
    add("to guess. A decision on them records the boundary, not a model")
    add("element.")
    add("")
    add("| ID | Where | Reason | Detail |")
    add("| --- | --- | --- | --- |")
    for entry in primitives.get("unmapped") or []:
        add("| `%s` | %s | %s | %s |"
            % (entry["id"], _where(entry.get("anchor")), entry["reason"],
               entry["detail"].replace("|", "\\|")))
    add("")
    return "\n".join(lines)


def operation_detail(operation, entry) -> list:
    lines = []
    add = lines.append
    flags = []
    if operation.get("mut_self"):
        flags.append("`&mut self`")
    if operation.get("guards"):
        flags.append("%d guard(s)" % len(operation["guards"]))
    else:
        flags.append("**no guard**")
    decision = (entry.get("decision") or "*open*") \
        if operation.get("required", True) else "not required"
    add("### `%s` — `%s` (tier %d)" % (operation["id"], operation["name"],
                                       tier(operation)))
    add("")
    add("- signature: `%s`" % operation["signature"])
    add("- where: %s" % _where(operation.get("anchor")))
    add("- flags: %s" % ", ".join(flags))
    add("- decision: **%s**" % decision)
    for guard in operation.get("guards") or []:
        add("  - guard: %s" % _guard_text(guard))
    for effect in operation.get("effects") or []:
        add("  - effect: %s" % _effect_text(effect))
    if operation.get("calls"):
        add("  - calls: %s" % ", ".join("`%s`" % c for c in operation["calls"]))
    if entry.get("note"):
        add("  - note: %s" % entry["note"])
    add("")
    return lines


def write_area_files(out: str, primitives: dict, chosen: dict,
                     include_tests: bool) -> list:
    """One file per area: required operations in detail plus their asserts."""
    areas = {}
    for operation in primitives.get("operations") or []:
        if operation.get("test") and not include_tests:
            continue
        if not operation.get("required", True):
            continue
        areas.setdefault(_area(operation["anchor"]["path"]), []).append(operation)
    index = []
    for name in sorted(areas):
        operations = sorted(areas[name], key=lambda op: (tier(op), op["id"]))
        by_id = {op["id"]: op for op in operations}
        lines = ["# %s — required operations" % name.replace("_", "/"), ""]
        lines.append("Decisions live in `decisions.yaml`; this file shows the")
        lines.append("detail. Assert invariants follow their operation.")
        lines.append("")
        for operation in operations:
            lines.extend(operation_detail(operation,
                                          chosen.get(operation["id"]) or {}))
        lines.append("## Assert invariants")
        lines.append("")
        lines.append("| ID | Follows | Text | Where |")
        lines.append("| --- | --- | --- | --- |")
        for invariant in primitives.get("invariants") or []:
            if invariant.get("kind") != "assert":
                continue
            if invariant.get("test") and not include_tests:
                continue
            scope = invariant.get("scope")
            if scope not in by_id:
                continue
            lines.append("| `%s` | `%s` | %s | %s |"
                         % (invariant["id"], scope,
                            invariant["text"].replace("|", "\\|"),
                            _where(invariant.get("anchor"))))
        lines.append("")
        rel = os.path.join("review", "%s.md" % name)
        path = os.path.join(out, "review", "%s.md" % name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        index.append(rel)
    return index


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Write the decision queue: review.md, review/, "
                    "review-index.json and decisions.yaml.")
    add_target_args(ap)
    ap.add_argument("--include-tests", action="store_true",
                    help="put test code back into the decision queue")
    ap.add_argument("--traps", default=DEFAULT_TRAPS,
                    help="known-traps file carried into review.md "
                         "(default: spec/traps.yaml shipped with the "
                         "conveyor)")
    args = ap.parse_args(argv)

    info, out, console, journal = prepare(args, "review")
    started = time.time()
    try:
        traps = load_traps(args.traps)
        primitives = load_primitives(out)
        existing = load_decisions(out)
        chosen = decision_map(existing)

        def keep_test(primitive):
            return args.include_tests or not primitive.get("test")

        entities = [e for e in primitives.get("entities") or [] if keep_test(e)]
        state = [s for s in primitives.get("state") or [] if keep_test(s)]
        operations = [o for o in primitives.get("operations") or []
                      if keep_test(o)]
        invariants = [i for i in primitives.get("invariants") or []
                      if keep_test(i)]

        required_ids = []
        for section in (entities, state):
            for primitive in section:
                required_ids.append(primitive["id"])
        for operation in operations:
            if operation.get("required", True):
                required_ids.append(operation["id"])
        for invariant in invariants:
            if invariant.get("kind") == "doc":
                required_ids.append(invariant["id"])

        decisions = []
        for primitive_id in required_ids:
            if primitive_id in chosen:
                decisions.append(chosen[primitive_id])
            else:
                decisions.append({
                    "id": primitive_id,
                    "decision": None,
                    "by": None,
                    "at": None,
                    "note": None,
                })
        # A human decision is never dropped: entries for primitives that left
        # the required set (renamed, now private, test) are kept at the end —
        # but only the ones somebody actually decided; null entries would
        # otherwise accumulate after every --include-tests run.
        kept = [chosen[primitive_id] for primitive_id in chosen
                if primitive_id not in required_ids
                and chosen[primitive_id].get("decision") not in (None, "")]
        decisions.extend(kept)
        orphans = [entry["id"] for entry in kept]

        queue = {1: [], 2: [], 3: []}
        for operation in operations:
            if operation.get("required", True):
                queue[tier(operation)].append(operation)

        def count_test(section):
            return sum(1 for p in primitives.get(section) or []
                       if p.get("test"))

        # The queue and the tier sum are not the same number, and the
        # difference must be accounted for, not hidden: only operations are
        # tiered. Entities, state fields and doc invariants ask for decisions
        # without landing in a tier.
        doc_invariants = [i for i in invariants if i.get("kind") == "doc"]
        breakdown = {
            "tiered_operations": sum(len(queue[number])
                                     for number in (1, 2, 3)),
            "entities": len(entities),
            "state": len(state),
            "doc_invariants": len(doc_invariants),
        }

        summary = {
            "required": len(required_ids),
            "breakdown": breakdown,
            "test": sum(count_test(section) for section in
                        ("entities", "state", "operations", "invariants")),
            "not_required": sum(1 for o in operations
                                if not o.get("required", True)),
            "asserts": sum(1 for i in invariants if i.get("kind") == "assert"),
        }

        payload = {
            "format": FORMAT_DECISIONS,
            "generated": now_iso(),
            "target": primitives.get("target"),
            "required_only": True,
            "decisions": decisions,
        }
        decisions_path = os.path.join(out, "decisions.yaml")
        dump_yaml(
            decisions_path, payload,
            header=(
                "# One entry per required primitive.\n"
                "# decision: approved | rejected | deferred (null = nobody has\n"
                "# decided yet); rejected and deferred need a note. An operation\n"
                "# with &mut self and no guard needs no_guard_ok: true plus a\n"
                "# note naming the enforcement point.\n"
                "# Not here: test code, private read-only operations, and\n"
                "# assert invariants (they follow their operation). Decisions\n"
                "# you wrote earlier are kept at the end of the list.\n"))

        review_path = os.path.join(out, "review.md")
        with open(review_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(build_review(primitives, decisions, chosen, queue,
                                  summary, traps, args.include_tests))

        areas = write_area_files(out, primitives, chosen, args.include_tests)

        index_payload = {
            "format": "dev-sec-skills/model-review-index/1",
            "generated": now_iso(),
            "target": primitives.get("target"),
            "required": len(required_ids),
            "tiers": {TIER_SHELL[number]: len(queue[number])
                      for number in (1, 2, 3)},
            "breakdown": breakdown,
            "traps": [trap["id"] for trap in traps.get("traps") or []],
            "entries": [
                {"id": operation["id"], "kind": "operation",
                 "name": operation["name"],
                 "owner": operation.get("owner"),
                 "path": operation["anchor"]["path"],
                 "start": operation["anchor"]["start"],
                 "end": operation["anchor"]["end"],
                 "tier": tier(operation),
                 "guards": len(operation.get("guards") or []),
                 "mut_self": operation.get("mut_self"),
                 "visibility": operation.get("visibility"),
                 "decision": (chosen.get(operation["id"]) or {}).get("decision")}
                for operation in sorted(
                    (op for op in operations if op.get("required", True)),
                    key=lambda op: (tier(op), op["id"]))
            ],
        }
        index_path = os.path.join(out, "review-index.json")
        write_json(index_path, index_payload)

        decided = sum(1 for entry in decisions if entry.get("decision"))
        console("review: %s" % review_path)
        console("  required to decide  %d" % len(required_ids))
        console("  already decided     %d" % decided)
        console("  tier 1 mut-self unguarded  %d" % len(queue[1]))
        console("  tier 2 public unguarded    %d" % len(queue[2]))
        console("  tier 3 guarded/read-only   %d" % len(queue[3]))
        console("  reconciled %d = %d tiered ops + %d entities + %d state"
                " + %d doc invariants"
                % (len(required_ids), breakdown["tiered_operations"],
                   breakdown["entities"], breakdown["state"],
                   breakdown["doc_invariants"]))
        console("  test excluded %d, not required %d, asserts %d"
                % (summary["test"], summary["not_required"],
                   summary["asserts"]))
        console("  known traps %d: %s"
                % (len(traps.get("traps") or []),
                   ", ".join(trap["id"] for trap in traps.get("traps") or [])))
        console("  area files %d, index %s" % (len(areas), index_path))
        if orphans:
            console("  ! decisions for ids outside the required set: %d (kept)"
                    % len(orphans))

        print("review: %d required, %d decided, %d orphans; tiers %d/%d/%d"
              % (len(required_ids), decided, len(orphans),
                 len(queue[1]), len(queue[2]), len(queue[3])))
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0,
            duration_ms=int((time.time() - started) * 1000),
            inputs=[{"path": os.path.join(out, "primitives.yaml"),
                     "sha256": sha256_file(os.path.join(out,
                                                        "primitives.yaml"))}],
            outputs=[{"path": decisions_path,
                      "sha256": sha256_file(decisions_path)},
                     {"path": review_path, "sha256": sha256_file(review_path)},
                     {"path": index_path, "sha256": sha256_file(index_path)}],
            counts={"required": len(required_ids), "decided": decided,
                    "orphans": len(orphans),
                    "tier1": len(queue[1]), "tier2": len(queue[2]),
                    "tier3": len(queue[3]),
                    "test_excluded": summary["test"],
                    "not_required": summary["not_required"],
                    "asserts": summary["asserts"]},
            status="ok",
        )
        return 0
    except ModelError as exc:
        console("review: %s" % exc)
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
