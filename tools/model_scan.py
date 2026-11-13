#!/usr/bin/env python3
"""Step 1: inventory a Rust project without interpreting it.

`scan` answers "what is here" and nothing else. It lexes every `.rs` file,
counts the declarations, and records what it could not read. A file it cannot
lex is listed with a reason; it is never silently skipped, because a missing
file would make every later count look better than it is.

Exit codes: 0 ok, 1 nothing to scan or every file failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from model_primitives import (
    FORMAT_INVENTORY, ModelError, add_target_args, journal_crash, now_iso,
    prepare, sha256_file, tool_block, write_json,
)
from rust_items import ParseError, parse_source
from rust_lexer import LexError

TCB_MARKERS = ("unsafe", "extern")


def _cargo(target: str) -> dict:
    path = os.path.join(target, "Cargo.toml")
    if not os.path.isfile(path):
        return {"present": False}
    data = {"present": True, "package": None, "edition": None}
    section = ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                continue
            if "=" not in line:
                continue
            key, value = [part.strip() for part in line.split("=", 1)]
            value = value.strip().strip('"').strip("'")
            if section == "package" and key == "name":
                data["package"] = value
            if section == "package" and key == "edition":
                data["edition"] = value
    return data


def scan_file(target: str, rel_path: str) -> dict:
    full = os.path.join(target, rel_path)
    row = {
        "path": rel_path,
        "bytes": os.path.getsize(full),
        "lines": 0,
        "sha256": sha256_file(full),
        "lex": "ok",
        "error": None,
        "structs": 0,
        "enums": 0,
        "impls": 0,
        "fns": 0,
        "pub_fns": 0,
        "mut_self_fns": 0,
        "tcb": [],
    }
    try:
        with open(full, "r", encoding="utf-8", newline="") as fh:
            source = fh.read()
    except UnicodeDecodeError as exc:
        row["lex"] = "error"
        row["error"] = "non-utf8: %s" % exc
        return row
    row["lines"] = source.count("\n") + (0 if source.endswith("\n") else 1)
    try:
        lexed, items, unsupported = parse_source(source)
    except LexError as exc:
        row["lex"] = "error"
        row["error"] = "lex: %s" % exc
        return row
    except ParseError as exc:
        row["lex"] = "error"
        row["error"] = "parse: %s" % exc
        return row

    owners = set()
    for item in items:
        kind = item["kind"]
        if kind == "struct":
            row["structs"] += 1
        elif kind == "enum":
            row["enums"] += 1
        elif kind == "fn":
            row["fns"] += 1
            if item["visibility"] == "public":
                row["pub_fns"] += 1
            if item.get("mut_self"):
                row["mut_self_fns"] += 1
            if item.get("owner"):
                owners.add(item["owner"])
    row["impls"] = len(owners)
    if unsupported:
        row["unsupported"] = unsupported
    markers = [tok.text for tok in lexed.tokens
               if tok.kind == "ident" and tok.text in TCB_MARKERS]
    row["tcb"] = sorted(set(markers))
    return row


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Inventory a Rust project for the model conveyor.")
    add_target_args(ap)
    args = ap.parse_args(argv)
    started = time.time()

    info, out, console, journal = prepare(args, "scan")
    try:
        from model_primitives import hash_inputs, iter_rust_files
        rel_paths = iter_rust_files(info["path"])
        if not rel_paths:
            raise ModelError("no .rs files under %s" % info["path"])

        rows = [scan_file(info["path"], rel) for rel in rel_paths]
        totals = {
            "files": len(rows),
            "files_ok": sum(1 for row in rows if row["lex"] == "ok"),
            "files_failed": sum(1 for row in rows if row["lex"] != "ok"),
            "lines": sum(row["lines"] for row in rows),
            "bytes": sum(row["bytes"] for row in rows),
            "structs": sum(row["structs"] for row in rows),
            "enums": sum(row["enums"] for row in rows),
            "impls": sum(row["impls"] for row in rows),
            "fns": sum(row["fns"] for row in rows),
            "pub_fns": sum(row["pub_fns"] for row in rows),
            "mut_self_fns": sum(row["mut_self_fns"] for row in rows),
            "tcb_markers": sum(len(row["tcb"]) for row in rows),
        }
        payload = {
            "format": FORMAT_INVENTORY,
            "generated": now_iso(),
            "tool": tool_block("model_scan"),
            "target": info,
            "cargo": _cargo(info["path"]),
            "files": rows,
            "totals": totals,
            "unsupported": [
                {"path": row["path"], "reason": row["error"]}
                for row in rows if row["lex"] != "ok"
            ],
        }
        path = os.path.join(out, "inventory.json")
        write_json(path, payload)

        console("scan: %s" % info["path"])
        if not args.quiet:
            console("  files      %d (%d ok, %d failed)"
                    % (totals["files"], totals["files_ok"],
                       totals["files_failed"]))
            console("  lines      %d" % totals["lines"])
            console("  structs    %d   enums %d   impls %d"
                    % (totals["structs"], totals["enums"], totals["impls"]))
            console("  fns        %d   public %d   &mut self %d"
                    % (totals["fns"], totals["pub_fns"],
                       totals["mut_self_fns"]))
            console("  tcb marks  %d" % totals["tcb_markers"])
            for row in rows:
                if row["lex"] != "ok":
                    console("  ! %s: %s" % (row["path"], row["error"]))

        status = "ok" if totals["files_ok"] else "error"
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0 if totals["files_ok"] else 1,
            duration_ms=int((time.time() - started) * 1000),
            inputs=hash_inputs(info["path"], rel_paths),
            outputs=[{"path": path, "sha256": sha256_file(path)}],
            counts=totals, status=status,
        )
        print("scan: %d files, %d failed, %d fns, %d mut-self"
              % (totals["files"], totals["files_failed"], totals["fns"],
                 totals["mut_self_fns"]))
        return 0 if totals["files_ok"] else 1
    except ModelError as exc:
        console("scan: %s" % exc)
        journal.write(argv=sys.argv[1:], target=info["path"],
                      target_commit=info["commit"], dirty=info["dirty"],
                      exit_code=2, duration_ms=int((time.time() - started) * 1000),
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
