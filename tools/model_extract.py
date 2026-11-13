#!/usr/bin/env python3
"""Step 2: derive model primitives from Rust source.

Every primitive carries an anchor: ``{path, start, end, sha256}``. The source
text itself is not copied into the artifact, so ``model/`` can be committed.

The extraction is deliberately conservative. What it cannot attribute becomes
an ``unmapped`` entry with a reason, never a guess:

* a file the lexer cannot read;
* a construct the item parser cannot delimit (``macro_rules``, a broken block);
* ``unsafe`` and ``extern``, which belong to the trusted computing base;
* a method call that looks like a state effect but is not in the closed list.

Exit codes: 0 ok, 1 the project produced no primitives at all, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from model_primitives import (
    FORMAT_PRIMITIVES, ModelError, add_target_args, is_test_path,
    journal_crash, make_anchor, now_iso, prepare, sha256_file, slug,
    tool_block, write_json, dump_yaml,
)
from rust_items import ParseError, parse_source
from rust_lexer import LexError

# Calls that mutate a field in place; the list is closed on purpose.
EFFECT_METHODS = {
    "insert", "push", "remove", "clear", "extend", "retain", "take",
    "replace", "get_or_insert", "entry", "pop", "swap_remove", "truncate",
}
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|="}
KEYWORD_CALLS = {
    "if", "while", "for", "match", "return", "let", "else", "in", "as",
    "assert", "assert_eq", "assert_ne", "debug_assert", "debug_assert_eq",
    "panic", "unreachable", "todo", "unimplemented", "vec", "format", "print",
    "println", "eprintln", "write", "writeln", "matches",
}
INVARIANT_WORDS = (
    "must", "never", "always", "invariant", "should", "cannot",
    "должен", "обязан", "никогда", "всегда", "инвариант", "не может",
)
DIVERGE_WORDS = {"return", "panic", "unreachable", "todo", "unimplemented",
                 "continue", "break", "Err"}


class Extractor:
    def __init__(self, target: str):
        self.target = target
        self.entities = []
        self.state = []
        self.operations = []
        self.invariants_list = []
        self.unmapped = []
        self._seen = {}

    # -- ids --------------------------------------------------------------

    def _id(self, prefix: str, name: str) -> str:
        base = "%s-%s" % (prefix, slug(name))
        candidate = base
        while candidate in self._seen:
            self._seen[base] += 1
            candidate = "%s-%d" % (base, self._seen[base])
        self._seen[candidate] = 1
        return candidate

    # -- per file ---------------------------------------------------------

    def add_file(self, rel_path: str) -> None:
        full = os.path.join(self.target, rel_path)
        try:
            with open(full, "r", encoding="utf-8", newline="") as fh:
                source = fh.read()
        except UnicodeDecodeError as exc:
            self._unmapped(rel_path, 1, 1, "non-utf8", str(exc))
            return
        try:
            lexed, items, unsupported = parse_source(source)
        except LexError as exc:
            line = max(1, getattr(exc, "line", 1))
            self._unmapped(rel_path, line, line, "lex-error",
                           "%s at %d:%d" % (exc.message, exc.line, exc.column))
            return
        except ParseError as exc:
            self._unmapped(rel_path, 1, 1, "parse-error", str(exc))
            return

        for entry in unsupported:
            self._unmapped(rel_path, entry["line"], entry["line"],
                           entry["reason"], entry["detail"])
        if any(tok.kind == "ident" and tok.text in ("unsafe", "extern")
               for tok in lexed.tokens):
            self._unmapped(rel_path, 1, max(1, len(lexed.lines)),
                           "tcb", "unsafe or extern: outside the model")

        fields = [item for item in items if item["kind"] == "struct"
                  and item.get("form") == "named"]
        for item in items:
            if item["kind"] in ("struct", "enum"):
                self._add_entity(rel_path, item)
        for struct in fields:
            self._add_state(rel_path, struct)
        for item in items:
            if item["kind"] == "fn":
                self._add_operation(rel_path, lexed, item)

    def _unmapped(self, path, start, end, reason, detail):
        entry = {
            "id": self._id("U", "%s-%s" % (path, reason)),
            "path": path,
            "reason": reason,
            "detail": detail,
            "anchor": self._anchor(path, start, end),
        }
        self.unmapped.append(entry)

    def _anchor(self, path, start, end):
        full = os.path.join(self.target, path)
        try:
            anchor = make_anchor(full, start, end)
            anchor["path"] = path
            return anchor
        except ModelError as exc:
            return {"path": path, "start": start, "end": end,
                    "sha256": None, "note": str(exc)}

    def _add_entity(self, path, item):
        entity = {
            "id": self._id("E", item["name"]),
            "kind": item["kind"],
            "name": item["name"],
            "visibility": item["visibility"],
            "anchor": self._anchor(path, item["start_line"], item["end_line"]),
            "required": True,
            "test": is_test_path(path),
            "status": "proposed",
        }
        if item["kind"] == "struct":
            entity["form"] = item.get("form", "named")
            entity["fields"] = [
                {"name": field["name"], "type": field["type"],
                 "visibility": field["visibility"]}
                for field in item.get("fields", [])
            ]
        else:
            entity["variants"] = [
                {"name": variant["name"]} for variant in item.get("variants", [])
            ]
        self.entities.append(entity)
        self.invariants_list.extend(
            self._doc_invariants(item, path, item["name"], entity["id"]))

    def _add_state(self, path, struct):
        for field in struct.get("fields", []):
            self.state.append({
                "id": self._id("S", "%s-%s" % (struct["name"], field["name"])),
                "entity": struct["name"],
                "field": field["name"],
                "type": field["type"],
                "visibility": field["visibility"],
                "anchor": self._anchor(path, field["line"], field["end_line"]),
                "read_by": [],
                "written_by": [],
                "required": True,
                "test": is_test_path(path),
                "status": "proposed",
            })

    def _add_operation(self, path, lexed, item):
        scope = item.get("owner") or item["name"]
        op_id = self._id("O", "%s-%s" % (scope, item["name"])) \
            if item.get("owner") else self._id("O", item["name"])
        body = item.get("body")
        # Bodyless operations (trait declarations) still get mappings, not
        # lists: `_field_uses` returns a dict, and every consumer calls `.get`.
        guards, effects, calls, field_uses = [], [], [], {}
        if body:
            body_start, body_end = body
            guards = self._guards(lexed, body_start, body_end)
            effects = self._effects(lexed, body_start, body_end)
            calls = self._calls(lexed, body_start, body_end)
            field_uses = self._field_uses(lexed, body_start, body_end)
        operation = {
            "id": op_id,
            "name": item["name"],
            "owner": item.get("owner"),
            "visibility": item["visibility"],
            "mut_self": bool(item.get("mut_self")),
            "receiver": item.get("receiver"),
            "signature": item["signature"],
            "anchor": self._anchor(path, item["start_line"], item["end_line"]),
            "guards": guards,
            "effects": effects,
            "calls": calls,
            # Only risk-bearing operations require a human decision: a private
            # read-only helper without effects is answered by its callers.
            "required": bool(item["visibility"] == "public"
                             or item.get("mut_self")),
            "test": is_test_path(path),
            "status": "proposed",
        }
        self.operations.append(operation)
        self.invariants_list.extend(
            self._doc_invariants(item, path, scope, op_id))
        for guard in guards:
            if guard["kind"] != "assert":
                continue
            # An assert invariant is not decided on its own: it follows the
            # operation that carries it (group decision, decided_by the op).
            self.invariants_list.append({
                "id": self._id("I", "%s-%s" % (op_id, slug(guard["condition"][:20]))),
                "kind": "assert",
                "scope": op_id,
                "text": guard["condition"],
                "anchor": guard["anchor"],
                "required": False,
                "test": is_test_path(path),
                "status": "proposed",
            })
        for state in self.state:
            if state["entity"] != item.get("owner"):
                continue
            hits = field_uses.get(state["field"])
            if not hits:
                continue
            if hits.get("read"):
                state["read_by"].append(op_id)
            if hits.get("write"):
                state["written_by"].append(op_id)

    def _doc_invariants(self, item, path, scope, owner_id):
        out = []
        docs = item.get("docs") or ""
        if not docs:
            return out
        for line in docs.splitlines():
            lowered = line.lower()
            if any(word in lowered for word in INVARIANT_WORDS):
                out.append({
                    "id": self._id("I", "%s-%s" % (owner_id,
                                                   slug(line.strip()[:24]))),
                    "kind": "doc",
                    "scope": owner_id,
                    "text": line.strip(),
                    "anchor": self._anchor(path, item["start_line"],
                                           item["start_line"]),
                    "required": True,
                    "test": is_test_path(path),
                    "status": "proposed",
                })
        return out

    # -- body analysis ----------------------------------------------------

    def _guards(self, lexed, first, last):
        t = lexed.tokens
        guards = []
        i = first
        while i <= last:
            tok = t[i]
            if tok.kind == "ident" and tok.text == "if":
                guard = self._if_guard(lexed, i, last)
                if guard:
                    guards.append(guard)
            if tok.kind == "ident" and tok.text in (
                    "assert", "debug_assert", "assert_eq", "assert_ne"):
                guard = self._macro_guard(lexed, i, last)
                if guard:
                    guards.append(guard)
            i += 1
        return guards

    def _if_guard(self, lexed, i, last):
        t = lexed.tokens
        j = i + 1
        depth = 0
        while j <= last:
            tok = t[j]
            if tok.kind == "punct":
                if tok.text in ("(", "["):
                    depth += 1
                elif tok.text in (")", "]"):
                    depth -= 1
                elif tok.text == "{" and depth == 0:
                    break
                elif tok.text == ";" and depth == 0:
                    return None
            j += 1
        if j > last:
            return None
        close = lexed.pairs.get(j)
        if close is None or close > last:
            return None
        condition = lexed.text_between(i + 1, j - 1).strip()
        first_stmt = j + 1
        while first_stmt < close and t[first_stmt].kind == "doc":
            first_stmt += 1
        reject_when = None
        if first_stmt < close and t[first_stmt].kind == "ident" \
                and t[first_stmt].text in DIVERGE_WORDS:
            reject_when = "true"
        else:
            after = close + 1
            if after <= last and t[after].kind == "ident" and t[after].text == "else":
                k = after + 1
                while k <= last and t[k].kind == "doc":
                    k += 1
                if k <= last and t[k].text == "{":
                    else_close = lexed.pairs.get(k)
                    first_else = k + 1
                    while first_else < else_close and t[first_else].kind == "doc":
                        first_else += 1
                    if first_else < else_close \
                            and t[first_else].kind == "ident" \
                            and t[first_else].text in DIVERGE_WORDS:
                        reject_when = "false"
        if reject_when is None:
            return None
        return {
            "kind": "early_return",
            "condition": condition,
            "reject_when": reject_when,
            "anchor": self._anchor_lines(lexed, i, close),
        }

    def _macro_guard(self, lexed, i, last):
        t = lexed.tokens
        if i + 1 > last or t[i + 1].text != "!":
            return None
        if i + 2 > last or t[i + 2].text not in ("(", "[", "{"):
            return None
        open_idx = i + 2
        close = lexed.pairs.get(open_idx)
        if close is None or close > last:
            return None
        args = self._split_args(lexed, open_idx + 1, close - 1)
        if not args:
            return None
        if t[i].text in ("assert_eq", "debug_assert_eq") and len(args) >= 2:
            condition = "%s == %s" % (args[0], args[1])
        elif t[i].text == "assert_ne" and len(args) >= 2:
            condition = "%s != %s" % (args[0], args[1])
        else:
            condition = args[0]
        return {
            "kind": "assert",
            "condition": condition.strip(),
            "reject_when": "false",
            "anchor": self._anchor_lines(lexed, i, close),
        }

    def _split_args(self, lexed, first, last):
        t = lexed.tokens
        parts, depth, start = [], 0, first
        for i in range(first, last + 1):
            tok = t[i]
            if tok.kind == "punct":
                if tok.text in ("(", "[", "{"):
                    depth += 1
                elif tok.text in (")", "]", "}"):
                    depth -= 1
                elif tok.text == "," and depth == 0:
                    parts.append(lexed.text_between(start, i - 1).strip())
                    start = i + 1
        if start <= last:
            parts.append(lexed.text_between(start, last).strip())
        return [part for part in parts if part]

    def _effects(self, lexed, first, last):
        t = lexed.tokens
        effects = []
        i = first
        while i <= last:
            if t[i].kind == "ident" and t[i].text == "self" \
                    and i + 1 <= last and t[i + 1].text == "." \
                    and i + 2 <= last and t[i + 2].kind == "ident":
                field = t[i + 2].text
                nxt = i + 3
                if nxt <= last and t[nxt].text in ASSIGN_OPS:
                    value, stop = self._statement_value(lexed, nxt + 1, last)
                    effects.append({
                        "kind": "assign",
                        "target": "self.%s" % field,
                        "operator": t[nxt].text,
                        "value": value,
                        "anchor": self._anchor_lines(lexed, i, stop),
                    })
                    i = stop
                elif nxt + 1 <= last and t[nxt].text == "." \
                        and t[nxt + 1].kind == "ident" \
                        and t[nxt + 1].text in EFFECT_METHODS:
                    method = t[nxt + 1].text
                    stop = nxt + 1
                    value = ""
                    if stop + 1 <= last and t[stop + 1].text == "(":
                        close = lexed.pairs.get(stop + 1)
                        if close is not None:
                            value = lexed.text_between(stop + 2, close - 1).strip()
                            stop = close
                    effects.append({
                        "kind": "method",
                        "method": method,
                        "target": "self.%s" % field,
                        "value": value,
                        "anchor": self._anchor_lines(lexed, i, stop),
                    })
                    i = stop
            i += 1
        for literal in self._struct_literal_writes(lexed, first, last):
            effects.append({
                "kind": "init",
                "target": "self.%s" % literal["field"],
                "value": literal["value"],
                "anchor": self._anchor_lines(lexed, literal["first"],
                                             literal["last"]),
            })
        return effects

    def _statement_value(self, lexed, start, last):
        t = lexed.tokens
        depth = 0
        i = start
        while i <= last:
            tok = t[i]
            if tok.kind == "punct":
                if tok.text in ("(", "[", "{"):
                    depth += 1
                elif tok.text in (")", "]", "}"):
                    if depth == 0:
                        break
                    depth -= 1
                elif tok.text == ";" and depth == 0:
                    break
            i += 1
        return lexed.text_between(start, i - 1).strip(), max(start, i - 1)

    def _calls(self, lexed, first, last):
        t = lexed.tokens
        names = []
        for i in range(first, last + 1):
            if t[i].kind != "ident" or t[i].text in KEYWORD_CALLS:
                continue
            if i + 1 <= last and t[i + 1].text == "(":
                if i > 0 and t[i - 1].text == "fn":
                    continue
                if t[i].text not in names:
                    names.append(t[i].text)
        return names[:50]

    def _struct_literal_writes(self, lexed, first, last):
        """`Self { field: value, ... }` counts as a write to each field."""
        t = lexed.tokens
        out = []
        i = first
        while i <= last:
            if t[i].kind == "ident" and t[i].text == "Self" \
                    and i + 1 <= last and t[i + 1].text == "{":
                open_idx = i + 1
                close = lexed.pairs.get(open_idx)
                if close is not None and close <= last:
                    j = open_idx + 1
                    while j < close:
                        if t[j].kind == "ident" and j + 1 < close \
                                and t[j + 1].text == ":":
                            k = j + 2
                            depth = 0
                            while k < close:
                                if t[k].text in ("(", "[", "{"):
                                    depth += 1
                                elif t[k].text in (")", "]", "}"):
                                    depth -= 1
                                elif t[k].text == "," and depth == 0:
                                    break
                                k += 1
                            out.append({
                                "field": t[j].text,
                                "value": lexed.text_between(j + 2, k - 1).strip(),
                                "first": j,
                                "last": max(j + 1, k - 1),
                            })
                            j = k + 1
                        elif t[j].kind == "ident" and (j + 1 >= close
                                                       or t[j + 1].text == ","):
                            # field shorthand: `Self { max_roles, ... }`
                            out.append({
                                "field": t[j].text,
                                "value": t[j].text,
                                "first": j,
                                "last": j,
                            })
                            j += 1
                        else:
                            j += 1
                    i = close + 1
                    continue
            i += 1
        return out

    def _field_uses(self, lexed, first, last):
        t = lexed.tokens
        uses = {}
        for i in range(first, last + 1):
            if t[i].kind == "ident" and t[i].text == "self" \
                    and i + 2 <= last and t[i + 1].text == "." \
                    and t[i + 2].kind == "ident":
                field = t[i + 2].text
                entry = uses.setdefault(field, {"read": False, "write": False})
                nxt = i + 3
                write = False
                if nxt <= last and t[nxt].text in ASSIGN_OPS:
                    write = True
                elif nxt + 1 <= last and t[nxt].text == "." \
                        and t[nxt + 1].kind == "ident" \
                        and t[nxt + 1].text in EFFECT_METHODS:
                    write = True
                if write:
                    entry["write"] = True
                else:
                    entry["read"] = True
        for literal in self._struct_literal_writes(lexed, first, last):
            entry = uses.setdefault(literal["field"],
                                    {"read": False, "write": False})
            entry["write"] = True
        return uses

    def _anchor_lines(self, lexed, first, last):
        start_line = lexed.tokens[first].line
        end_line = lexed.tokens[min(last, len(lexed.tokens) - 1)].line
        path = self._current_path
        return self._anchor(path, start_line, end_line)

    _current_path = ""


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Extract model primitives from Rust source.")
    add_target_args(ap)
    args = ap.parse_args(argv)
    started = time.time()

    info, out, console, journal = prepare(args, "extract")
    extractor = Extractor(info["path"])
    try:
        from model_primitives import hash_inputs, iter_rust_files
        rel_paths = iter_rust_files(info["path"])
        if not rel_paths:
            raise ModelError("no .rs files under %s" % info["path"])
        for rel in rel_paths:
            extractor._current_path = rel
            extractor.add_file(rel)

        counts = {
            "files": len(rel_paths),
            "entities": len(extractor.entities),
            "state": len(extractor.state),
            "operations": len(extractor.operations),
            "mut_self_ops": sum(1 for op in extractor.operations
                                if op["mut_self"]),
            "guards": sum(len(op["guards"]) for op in extractor.operations),
            "effects": sum(len(op["effects"]) for op in extractor.operations),
            "invariants": len(extractor.invariants_list),
            "unmapped": len(extractor.unmapped),
            "anchors": (len(extractor.entities) + len(extractor.state)
                        + len(extractor.operations) + len(extractor.unmapped)
                        + len(extractor.invariants_list)),
        }
        payload = {
            "format": FORMAT_PRIMITIVES,
            "generated": now_iso(),
            "tool": tool_block("model_extract"),
            "target": info,
            "entities": extractor.entities,
            "state": extractor.state,
            "operations": extractor.operations,
            "invariants": extractor.invariants_list,
            "unmapped": extractor.unmapped,
            "counts": counts,
        }
        path = os.path.join(out, "primitives.yaml")
        dump_yaml(path, payload, header=(
            "# Generated by tools/model_extract.py. Do not edit: decisions live\n"
            "# in decisions.yaml. Anchors are line ranges plus a snippet hash;\n"
            "# no source text is stored here.\n"))

        console("extract: %s" % info["path"])
        if not args.quiet:
            console("  entities   %d   state %d"
                    % (counts["entities"], counts["state"]))
            console("  operations %d   (&mut self %d)"
                    % (counts["operations"], counts["mut_self_ops"]))
            console("  guards     %d   effects %d"
                    % (counts["guards"], counts["effects"]))
            console("  unmapped   %d" % counts["unmapped"])
            for entry in extractor.unmapped:
                console("  ! %s:%d %s" % (entry["path"],
                                          entry["anchor"]["start"],
                                          entry["reason"]))

        status = "ok" if counts["operations"] or counts["entities"] else "error"
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=0 if status == "ok" else 1,
            duration_ms=int((time.time() - started) * 1000),
            inputs=hash_inputs(info["path"], rel_paths),
            outputs=[{"path": path, "sha256": sha256_file(path)}],
            counts=counts, status=status,
        )
        print("extract: %d entities, %d operations, %d guards, %d unmapped"
              % (counts["entities"], counts["operations"], counts["guards"],
                 counts["unmapped"]))
        return 0 if status == "ok" else 1
    except ModelError as exc:
        console("extract: %s" % exc)
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
