#!/usr/bin/env python3
"""Step 6: assemble MODEL.md from artifacts, not from memory.

Every section of the report is derived from a file written by an earlier step:
the inventory, the primitives, the decisions, the generated model and the check
results. The status ladder is printed with the reason it landed where it did.

Exit codes: 0 ok, 1 required artifacts are missing, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from model_primitives import (
    ModelError, add_target_args, journal_crash, load_decisions, load_json,
    load_primitives, prepare, sha256_file,
)


def _where(anchor) -> str:
    if not anchor:
        return "—"
    return "`%s:%s-%s`" % (anchor.get("path"), anchor.get("start"),
                           anchor.get("end"))


def _decision(chosen, primitive_id) -> str:
    entry = chosen.get(primitive_id) or {}
    value = entry.get("decision") or "open"
    if entry.get("no_guard_ok"):
        value += " (no-guard-ok)"
    return value


def build_report(primitives, decisions, model, checks, inventory):
    chosen = (decisions or {}).get("decisions") or []
    chosen = {entry["id"]: entry for entry in chosen if isinstance(entry, dict)}
    counts = primitives.get("counts") or {}
    target = primitives.get("target") or {}
    status = (checks or {}).get("status", "open")
    lines = []
    add = lines.append

    add("# Formal model derived from `%s`" % target.get("name"))
    add("")
    add("Target: `%s`  " % target.get("path"))
    add("Commit: `%s`%s  " % (target.get("commit") or "none",
                              " (dirty working tree)" if target.get("dirty")
                              else ""))
    add("Generated: %s  " % primitives.get("generated"))
    add("Tool: `model_report` %s" % ((primitives.get("tool") or {})
                                     .get("version", "?")))
    add("")
    add("## 1. Status")
    add("")
    add("| Element | Value |")
    add("| --- | --- |")
    add("| Status | **%s** |" % status)
    add("| Reason | %s |" % reason_for(status, checks))
    add("| Anchors | %s (stale %s, missing %s) |"
        % ((checks or {}).get("counts", {}).get("anchors", 0),
           (checks or {}).get("counts", {}).get("stale", 0),
           (checks or {}).get("counts", {}).get("missing", 0)))
    add("| Approved primitives | %s of %s |"
        % (len([1 for primitive_id, entry in chosen.items()
                if entry.get("decision") == "approved"]), len(chosen)))
    add("")
    add("Ladder: `open` → `tested` → `model-checked` → `proven`. This run is")
    add("`%s` because %s" % (status, reason_for(status, checks)))
    add("")
    add("`model-checked` is not emitted by V0: there is no bounded state")
    add("enumerator behind it yet. `proven` would require Rodin or ProB and is")
    add("not attempted here.")
    add("")

    add("## 2. Scope and borders")
    add("")
    add("The model is derived from the declarations and bodies of the Rust")
    add("project above. It covers:")
    add("")
    add("- state declared as named `struct` fields;")
    add("- operations declared as `fn`, with their receivers and visibility;")
    add("- guards recognised as early returns, `assert!` and `debug_assert!`;")
    add("- effects recognised as field assignment and a closed list of mutating")
    add("  methods (`insert`, `push`, `remove`, `clear`, `extend`, `retain`,")
    add("  `take`, `replace`, `pop`, `truncate`);")
    add("- candidate invariants from `assert!` and from doc comments that use")
    add("  invariant language.")
    add("")
    add("It does not cover: macro-generated items, `unsafe`/`extern` blocks")
    add("(listed as TCB), or any expression whose meaning the extractor cannot")
    add("read. Those appear in section 8 and are counted, not dropped.")
    add("")

    add("## 3. Source")
    add("")
    totals = (inventory or {}).get("totals") or {}
    add("| Files | Lines | Structs | Enums | Fns | Public | `&mut self` |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    add("| %s | %s | %s | %s | %s | %s | %s |"
        % (totals.get("files", "?"), totals.get("lines", "?"),
           totals.get("structs", "?"), totals.get("enums", "?"),
           totals.get("fns", "?"), totals.get("pub_fns", "?"),
           totals.get("mut_self_fns", "?")))
    add("")

    add("## 4. Sets and state")
    add("")
    for entity in primitives.get("entities") or []:
        if entity["kind"] == "enum":
            add("- set `%s` = {%s} — %s — %s"
                % (entity["name"],
                   ", ".join(v["name"] for v in entity.get("variants") or []),
                   _decision(chosen, entity["id"]),
                   _where(entity.get("anchor"))))
    add("")
    add("| State | Type | Read by | Written by | Decision | Where |")
    add("| --- | --- | --- | --- | --- | --- |")
    for state in primitives.get("state") or []:
        add("| `%s.%s` | `%s` | %s | %s | %s | %s |"
            % (state.get("entity"), state.get("field"), state.get("type"),
               ", ".join(state.get("read_by") or []) or "—",
               ", ".join(state.get("written_by") or []) or "—",
               _decision(chosen, state["id"]), _where(state.get("anchor"))))
    add("")

    add("## 5. Operations")
    add("")
    for operation in primitives.get("operations") or []:
        decision = (chosen.get(operation["id"]) or {}).get("decision")
        if decision != "approved":
            continue
        add("### `%s`" % operation["name"])
        add("")
        add("- id: `%s`" % operation["id"])
        add("- signature: `%s`" % operation["signature"])
        add("- where: %s" % _where(operation.get("anchor")))
        if operation.get("guards"):
            add("- guards:")
            for guard in operation["guards"]:
                add("  - `%s` — reject when %s (%s)"
                    % (guard["condition"], guard["reject_when"],
                       _where(guard.get("anchor"))))
        else:
            add("- guards: none; `no_guard_ok` = %s"
                % bool((chosen.get(operation["id"]) or {}).get("no_guard_ok")))
        if operation.get("effects"):
            add("- effects:")
            for effect in operation["effects"]:
                if effect["kind"] == "method":
                    text = "`%s.%s(%s)`" % (effect["target"],
                                            effect.get("method"),
                                            effect.get("value"))
                elif effect["kind"] == "init":
                    text = "`%s := %s` (init)" % (effect["target"],
                                                  effect.get("value"))
                else:
                    text = "`%s %s %s`" % (effect["target"],
                                           effect.get("operator", "="),
                                           effect.get("value"))
                add("  - %s (%s)" % (text, _where(effect.get("anchor"))))
        add("")

    add("## 6. Candidate invariants")
    add("")
    add("| ID | Kind | Text | Decision | Where |")
    add("| --- | --- | --- | --- | --- |")
    for invariant in primitives.get("invariants") or []:
        add("| `%s` | %s | %s | %s | %s |"
            % (invariant["id"], invariant["kind"],
               invariant["text"].replace("|", "\\|"),
               _decision(chosen, invariant["id"]),
               _where(invariant.get("anchor"))))
    add("")
    add("A candidate is a hypothesis. `approved` means the sentence is worth")
    add("proving, not that the code enforces it.")
    add("")

    add("## 7. Machine verification")
    add("")
    add("| Check | Status | Detail |")
    add("| --- | --- | --- |")
    for check in (checks or {}).get("checks") or []:
        add("| `%s` | %s | %s |" % (check["id"], check["status"],
                                    check["detail"]))
    add("")
    failures = [check for check in (checks or {}).get("checks") or []
                if check["status"] == "fail"]
    if failures:
        add("Findings that block the status:")
        add("")
        for check in failures:
            for item in check.get("items") or []:
                add("- `%s`: %s" % (check["id"], item))
        add("")
    warnings = [check for check in (checks or {}).get("checks") or []
                if check["status"] == "warn"]
    if warnings:
        add("Warnings (do not block, do not disappear):")
        add("")
        for check in warnings:
            for item in check.get("items") or []:
                add("- `%s`: %s" % (check["id"], item))
        add("")

    add("## 8. Excluded and unmapped")
    add("")
    excluded = (model or {}).get("excluded") or {}
    add("| Bucket | Count | IDs |")
    add("| --- | --- | --- |")
    for bucket in ("proposed", "rejected", "deferred", "test", "not_required",
                   "unmapped"):
        ids = excluded.get(bucket) or []
        shown = ", ".join("`%s`" % value for value in ids[:12])
        if len(ids) > 12:
            shown += ", …"
        add("| %s | %d | %s |" % (bucket, len(ids), shown or "—"))
    add("")
    for entry in primitives.get("unmapped") or []:
        add("- `%s` %s — %s: %s" % (entry["id"], _where(entry.get("anchor")),
                                    entry["reason"], entry["detail"]))
    add("")

    add("## 9. Evidence registry")
    add("")
    add("| Artifact | SHA-256 |")
    add("| --- | --- |")
    for name in ("inventory.json", "primitives.yaml", "decisions.yaml",
                 "review.md", "generated/model.json", "generated/model.sys",
                 "checks/results.json"):
        path = os.path.join(primitives.get("_out", ""), name)
        digest = sha256_file(path) if os.path.isfile(path) else "missing"
        add("| `%s` | `%s` |" % (name, digest))
    add("")

    add("## 10. Limitations")
    add("")
    for limitation in (checks or {}).get("limitations") or []:
        add("- %s" % limitation)
    add("- Guards are recognised syntactically. An `if` that returns early is")
    add("  a guard; a call to a helper that returns early is not.")
    add("- `no_guard_ok` is a human assertion with a note, not a proof.")
    add("")

    add("## 11. Reproduce")
    add("")
    add("```bash")
    add("make model-scan    TARGET=<target>")
    add("make model-extract TARGET=<target>")
    add("make model-review  TARGET=<target>")
    add("# edit model/decisions.yaml")
    add("make model-gen     TARGET=<target>")
    add("make model-check   TARGET=<target>")
    add("make model-report  TARGET=<target>")
    add("```")
    add("")
    return "\n".join(lines)


def reason_for(status, checks):
    if not checks:
        return "the check step has not run"
    counts = checks.get("counts") or {}
    failures = [check["id"] for check in checks.get("checks") or []
                if check["status"] == "fail"]
    if status == "tested":
        return ("every mandatory check passed (%d anchors, %d stale, %d "
                "undecided)" % (counts.get("anchors", 0),
                                counts.get("stale", 0),
                                counts.get("undecided", 0)))
    return "mandatory checks failed: %s" % (", ".join(failures) or "none")


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Write MODEL.md from artifacts.")
    add_target_args(ap)
    args = ap.parse_args(argv)

    info, out, console, journal = prepare(args, "report")
    started = time.time()
    try:
        primitives = load_primitives(out)
        primitives["_out"] = out
        decisions = load_decisions(out)
        model_path = os.path.join(out, "generated", "model.json")
        checks_path = os.path.join(out, "checks", "results.json")
        if not os.path.isfile(model_path):
            raise ModelError("missing generated/model.json; run model-gen")
        if not os.path.isfile(checks_path):
            raise ModelError("missing checks/results.json; run model-check")
        model = load_json(model_path)
        checks = load_json(checks_path)
        inventory_path = os.path.join(out, "inventory.json")
        inventory = load_json(inventory_path) if os.path.isfile(inventory_path) \
            else {}

        text = build_report(primitives, decisions, model, checks, inventory)
        path = os.path.join(out, "MODEL.md")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

        console("report: %s" % path)
        console("  status %s" % checks.get("status"))
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0, duration_ms=int((time.time() - started) * 1000),
            outputs=[{"path": path, "sha256": sha256_file(path)}],
            counts={"checks": len(checks.get("checks") or [])}, status="ok",
        )
        print("report: %s (%s)" % (path, checks.get("status")))
        return 0
    except ModelError as exc:
        console("report: %s" % exc)
        journal.write(argv=sys.argv[1:], target=info["path"],
                      target_commit=info["commit"], dirty=info["dirty"],
                      exit_code=1,
                      duration_ms=int((time.time() - started) * 1000),
                      status="error", error=str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 - a crash must still be journaled
        journal_crash(console, journal, exc, started, argv=sys.argv[1:],
                      target=info["path"], target_commit=info["commit"],
                      dirty=info["dirty"])
        return 2
    finally:
        console.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
