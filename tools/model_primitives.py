#!/usr/bin/env python3
"""Shared primitives for the code-to-model conveyor.

Everything here is stdlib plus PyYAML (already a dependency of the repository's
other gates). No parser generator, no tree-sitter: the Rust lexer lives in
``tools/rust_lexer.py`` and is written by hand.

The module owns four things every conveyor step needs:

* anchors: ``{path, start, end, sha256}`` over a line range, with no source text;
* the artifact clock and the tool identity, so two runs can be compared;
* a minimal JSON-schema validator for the three artifact schemas;
* the two-channel journal: ``runs/<ts>/events.jsonl`` and ``console.log``.

Exit codes used by every tool in the conveyor: 0 ok, 1 the artifact fails its
own gate, 2 usage, input or environment error.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

try:  # PyYAML is required by the repository's other gates as well.
    import yaml
except ImportError:  # pragma: no cover - the message is the point
    sys.stderr.write(
        "model: PyYAML is required (it is already used by make verify).\n"
        "       install it with: python3 -m pip install pyyaml\n"
    )
    raise SystemExit(2)

FORMAT_PRIMITIVES = "dev-sec-skills/model-primitives/1"
FORMAT_INVENTORY = "dev-sec-skills/model-inventory/1"
FORMAT_DECISIONS = "dev-sec-skills/model-decisions/1"
FORMAT_MODEL = "dev-sec-skills/model/1"
FORMAT_CHECKS = "dev-sec-skills/model-checks/1"
FORMAT_HANDOFF = "dev-sec-skills/model-handoff/1"

TOOL_VERSION = "0.1.0"

STATUS_ORDER = ("open", "tested", "model-checked", "proven")

DECISIONS = ("approved", "rejected", "deferred")

SKIP_DIRS = {".git", "target", "node_modules", "vendor", ".cargo", ".venv",
             "__pycache__"}

# Test code is excluded from the review queue by default: 6,204 of 19,235
# operations and 18,206 of 34,816 invariants in the first real run were test
# noise. Path-based, because `#[cfg(test)]` is not evaluated.
TEST_PATH = re.compile(
    r"(^|/)(tests?|testing|benches?|examples?)/|_tests?\.rs$|tests\.rs$")


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path or ""))


class ModelError(Exception):
    """A gate failure that the caller must see; the message says what."""


# --------------------------------------------------------------------- hashing

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------------------------------------------------- snippets

def read_source(path: str) -> str:
    """Read a source file as UTF-8 without newline translation."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def split_lines(text: str) -> list:
    """Split on LF and drop a trailing CR, without inventing a last line."""
    lines = text.split("\n")
    if lines and lines[-1] == "" and text.endswith("\n"):
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def snippet(path: str, start: int, end: int) -> str:
    """The exact lines ``start..end`` (1-based, inclusive), joined by LF."""
    try:
        lines = split_lines(read_source(path))
    except (OSError, UnicodeDecodeError) as exc:
        # A file the anchors cannot be computed against at all is a model
        # error, not a crash: extraction saw the same file and anchored it,
        # so check time must degrade to a state, not a traceback.
        raise ModelError("cannot read %s: %s" % (path, exc)) from exc
    if start < 1 or end < start or end > len(lines):
        raise ModelError(
            "anchor out of range for %s: %d..%d of %d lines"
            % (path, start, end, len(lines))
        )
    return "\n".join(lines[start - 1:end])


def make_anchor(path: str, start: int, end: int) -> dict:
    """An anchor carries no source text: path, line range and snippet hash."""
    return {
        "path": path,
        "start": start,
        "end": end,
        "sha256": sha256_text(snippet(path, start, end)),
    }


def anchor_state(anchor: dict, root: str) -> tuple:
    """Return ``("fresh"|"stale"|"missing"|"unanchored", detail)`` for one anchor."""
    path = anchor.get("path")
    if not path:
        return "missing", "anchor has no path"
    if not anchor.get("sha256"):
        # Distinct from "stale": an anchor without a hash was never valid,
        # so it cannot mean the file changed (the EOF off-by-one once
        # reported an unchanged file stale forever through this path).
        return "unanchored", "anchor could not be hashed at extraction"
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.isfile(full):
        return "missing", "file not found: %s" % path
    try:
        current = sha256_text(snippet(full, anchor.get("start", 0),
                                      anchor.get("end", 0)))
    except ModelError as exc:
        return "stale", str(exc)
    if current != anchor.get("sha256"):
        return "stale", "snippet changed since extraction: %s" % path
    return "fresh", ""


# --------------------------------------------------------------------- yaml/json

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ModelError("%s: top level must be a mapping" % path)
    return data


def dump_yaml(path: str, data: dict, header: str = "") -> None:
    text = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=False,
        width=100,
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        if header:
            fh.write(header.rstrip("\n") + "\n")
        fh.write(text)


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------------- clock

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def run_id() -> str:
    env = os.environ.get("MODEL_RUN_ID")
    if env:
        return env
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


# ------------------------------------------------------------------ target info

def git(target: str, *args: str) -> str | None:
    import subprocess
    try:
        done = subprocess.run(
            ["git", "-C", target] + list(args),
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def target_info(target: str) -> dict:
    target = os.path.abspath(target)
    if not os.path.isdir(target):
        raise ModelError("target is not a directory: %s" % target)
    commit = git(target, "rev-parse", "HEAD")
    porcelain = git(target, "status", "--porcelain")
    return {
        "path": target,
        "name": os.path.basename(os.path.normpath(target)),
        "commit": commit,
        "dirty": bool(porcelain) if porcelain is not None else None,
        "is_git": commit is not None,
    }


def iter_rust_files(target: str, limit: int = 20000):
    """Yield repository-relative `.rs` paths in a deterministic order."""
    found = []
    for root, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.startswith(".git"))
        for name in sorted(files):
            if name.endswith(".rs"):
                full = os.path.join(root, name)
                found.append(os.path.relpath(full, target))
                if len(found) >= limit:
                    return found
    return found


# ------------------------------------------------------------------- artifacts

def rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def default_out(target: str) -> str:
    return os.path.join(target, "model")


def ensure_artifact(out: str, name: str) -> str:
    path = os.path.join(out, name)
    if not os.path.isfile(path):
        raise ModelError(
            "missing %s in %s; run the previous step first" % (name, out))
    return path


def load_primitives(out: str) -> dict:
    path = ensure_artifact(out, "primitives.yaml")
    data = load_yaml(path)
    fmt = data.get("format")
    if fmt != FORMAT_PRIMITIVES:
        raise ModelError("%s: unexpected format %r" % (path, fmt))
    return data


def load_decisions(out: str) -> dict:
    path = os.path.join(out, "decisions.yaml")
    if not os.path.isfile(path):
        return {"format": FORMAT_DECISIONS, "decisions": []}
    data = load_yaml(path)
    fmt = data.get("format")
    if fmt != FORMAT_DECISIONS:
        raise ModelError("%s: unexpected format %r" % (path, fmt))
    return data


def decision_map(decisions: dict) -> dict:
    out = {}
    for entry in decisions.get("decisions") or []:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ModelError("decisions: every entry needs an id")
        out[entry["id"]] = entry
    return out


def bounds_of(out: str) -> dict | None:
    path = os.path.join(out, "bounds.yaml")
    if not os.path.isfile(path):
        return None
    data = load_yaml(path)
    bounds = data.get("bounds")
    if not isinstance(bounds, dict) or not bounds:
        raise ModelError("bounds.yaml: missing a non-empty `bounds` mapping")
    if not bounds.get("rationale"):
        raise ModelError(
            "bounds.yaml: every bound needs a `rationale`; numbers without a "
            "reason are not a bound, they are a guess")
    return data


# ------------------------------------------------------------------ tool identity

def tool_block(tool: str) -> dict:
    return {"name": tool, "version": TOOL_VERSION, "python": sys.version.split()[0]}


# ------------------------------------------------------------------ console+log

class Console:
    """Print to stdout and mirror the same bytes into console.log."""

    def __init__(self, out: str, step: str, run_id_value=None):
        self.run_id = run_id_value or run_id()
        self.dir = os.path.join(out, "runs", self.run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "console.log")
        self._fh = open(self.path, "a", encoding="utf-8", newline="\n")
        self.step = step

    def __call__(self, *parts) -> None:
        line = " ".join(str(p) for p in parts)
        print(line)
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class RunJournal:
    """Append-only ``events.jsonl``; one event per tool invocation."""

    def __init__(self, out: str, step: str, run_id_value=None):
        self.run_id = run_id_value or run_id()
        self.dir = os.path.join(out, "runs", self.run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "events.jsonl")
        self.step = step
        self.seq = 0
        if os.path.isfile(self.path):
            with open(self.path, "r", encoding="utf-8") as fh:
                self.seq = sum(1 for line in fh if line.strip())

    def write(self, *, argv, target, target_commit, dirty, exit_code,
              duration_ms, inputs=None, outputs=None, counts=None,
              status="ok", error=None, environment=None) -> dict:
        import time
        self.seq += 1
        event = {
            "ts": now_iso(),
            "run_id": self.run_id,
            "seq": self.seq,
            "step": self.step,
            "argv": list(argv),
            "cmd": " ".join([sys.executable] + list(argv)),
            "cwd": os.getcwd(),
            "target": target,
            "target_commit": target_commit,
            "target_dirty": dirty,
            "environment": environment,
            "exit": exit_code,
            "duration_ms": duration_ms,
            "inputs": inputs or [],
            "outputs": outputs or [],
            "counts": counts or {},
            "status": status,
            "error": error,
            "tool": tool_block("model_%s" % self.step),
        }
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n")
        return event


def journal_crash(console, journal, exc, started, *, argv, target,
                  target_commit, dirty) -> None:
    """Record an unexpected crash in both channels.

    A step that dies outside ``ModelError`` must still leave an event: a
    0-byte console log with no ``events.jsonl`` line hides the failure from
    the metrics and the handoff.
    """
    import time
    import traceback
    console("%s: internal error: %s: %s"
            % (journal.step, type(exc).__name__, exc))
    console(traceback.format_exc())
    journal.write(
        argv=argv, target=target, target_commit=target_commit, dirty=dirty,
        exit_code=2, duration_ms=int((time.time() - started) * 1000),
        status="error", error="%s: %s" % (type(exc).__name__, exc))


def hash_inputs(root: str, paths) -> list:
    out = []
    for path in paths:
        full = path if os.path.isabs(path) else os.path.join(root, path)
        if os.path.isfile(full):
            out.append({
                "path": rel(full, root),
                "sha256": sha256_file(full),
            })
    return out


def hash_outputs(paths) -> list:
    out = []
    for path in paths:
        if os.path.isfile(path):
            out.append({"path": path, "sha256": sha256_file(path)})
    return out


# ---------------------------------------------------------------- schema checks

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def validate_instance(instance, schema, where="$") -> list:
    """A deliberately small JSON-schema subset, enough for our artifacts.

    Supports: type, required, properties, additionalProperties (bool),
    items, enum, const, minimum, maximum, pattern, minLength, minItems,
    oneOf (first match wins for validation, not semantics).
    """
    errors = []

    if "oneOf" in schema:
        branches = schema["oneOf"]
        ok = False
        for branch in branches:
            if not validate_instance(instance, branch, where):
                ok = True
                break
        if not ok:
            errors.append("%s: matches none of the allowed shapes" % where)
        return errors

    if "type" in schema:
        want = schema["type"]
        wants = want if isinstance(want, list) else [want]
        accepted = tuple(_TYPES[t] for t in wants if t in _TYPES)
        if accepted and not isinstance(instance, accepted):
            errors.append("%s: expected %s, got %s"
                          % (where, want, type(instance).__name__))
            return errors
        if "integer" in wants and isinstance(instance, bool):
            errors.append("%s: expected integer, got boolean" % where)
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r is not one of %r"
                      % (where, instance, schema["enum"]))

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected constant %r" % (where, schema["const"]))

    if isinstance(instance, str):
        if "pattern" in schema:
            import re
            if not re.search(schema["pattern"], instance):
                errors.append("%s: %r does not match %s"
                              % (where, instance, schema["pattern"]))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than %d" % (where, schema["minLength"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: below minimum %r" % (where, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: above maximum %r" % (where, schema["maximum"]))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than %d items" % (where, schema["minItems"]))
        if "items" in schema:
            for idx, item in enumerate(instance):
                errors.extend(validate_instance(item, schema["items"],
                                                "%s[%d]" % (where, idx)))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required key %r" % (where, key))
        props = schema.get("properties") or {}
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_instance(value, props[key],
                                                "%s.%s" % (where, key)))
            elif schema.get("additionalProperties") is False:
                errors.append("%s: unexpected key %r" % (where, key))

    return errors


def validate_file(path: str, schema_path: str) -> list:
    return validate_instance(load_json(path), load_json(schema_path),
                             where=os.path.basename(path))


# ---------------------------------------------------------------------- helpers

def slug(text: str) -> str:
    out = []
    for ch in text:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        else:
            out.append("-")
    cleaned = "".join(out).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "item"


def human_lines(n: int) -> str:
    return "%d" % n


def add_target_args(ap, require_target: bool = True) -> None:
    ap.add_argument("--target", required=require_target,
                    help="Rust project to model")
    ap.add_argument("--out", default=None,
                    help="artifact directory (default: <target>/model)")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the final line")


def resolve_out(args) -> str:
    out = args.out or default_out(os.path.abspath(args.target))
    return os.path.abspath(out)


def prepare(args, step: str):
    """Resolve the target, the artifact directory and the two log channels."""
    info = target_info(args.target)
    out = resolve_out(args)
    os.makedirs(out, exist_ok=True)
    # One id for both channels: a second boundary between the two calls would
    # otherwise split console.log and events.jsonl across two run directories.
    label = run_id()
    console = Console(out, step, label)
    journal = RunJournal(out, step, label)
    return info, out, console, journal
