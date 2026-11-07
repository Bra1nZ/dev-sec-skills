#!/usr/bin/env python3
"""Deterministic fuzz adapter — one recorded run, one replayable artifact.

Runs a command over a seed corpus and over inputs mutated from that corpus
with a fixed seed, checks each execution against an explicit oracle, and
writes a JSON record (schemas/fuzz-run.schema.json) plus the failing inputs
and their captured output.

This is not a coverage-guided fuzzer: mutations are random edits, and the
adapter says so in every record. It exists so a fuzz run has an oracle, a
budget, a fixed seed and an artifact that a reviewer can replay, instead of a
terminal session nobody can reconstruct.

Oracle rules (repeatable; a run is a finding when any rule matches):

  exit:N                 violation unless the exit code is N
  exit-not-in:N,M        violation when the exit code is not in the list
  stdout-contains:TEXT   violation when TEXT appears in stdout
  stderr-contains:TEXT   violation when TEXT appears in stderr
  timeout                violation when the run exceeded --timeout

The target command gets the input path substituted for `@INPUT@` (or appended
when the placeholder is absent) and the same bytes on stdin. The command is
split with shlex and run without a shell.

Determinism: the corpus is read in sorted path order and the mutator is
random.Random(seed). `executions_digest` is the SHA-256 of the ordered input
hashes, so two runs with the same corpus and seed must produce the same digest.
A different target or a changed corpus changes it, which is the point.

Exit codes: 0 clean, 1 findings, 2 tool/usage error.

Usage:
    python3 tools/fuzz_run.py --target 'python3 target.py @INPUT@' \
        --corpus corpus/ --record out/fuzz.json --seed 20261107 --runs 200 \
        --oracle exit-not-in:0,1 --oracle 'stderr-contains:Traceback'
"""

import argparse
import hashlib
import json
import os
import random
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime

SCHEMA_VERSION = "1"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _walk(root):
    out = []
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(base, name)
            if os.path.isfile(path):
                out.append(path)
    return sorted(out)


def load_corpus(root):
    if not os.path.isdir(root):
        raise SystemExit("corpus not found: %s" % root)
    files = _walk(root)
    if not files:
        raise SystemExit("corpus is empty: %s" % root)
    manifest, blobs = [], []
    for path in files:
        data = open(path, "rb").read()
        rel = os.path.relpath(path, root)
        rel = rel.replace(os.sep, "/")
        manifest.append({"path": rel, "sha256": _sha256(data), "size": len(data)})
        blobs.append(data)
    return manifest, blobs


def mutate(rng, data):
    """A small deterministic mutator; random edits, not coverage-guided."""
    out = bytearray(data)
    for _ in range(rng.randint(1, 4)):
        choice = rng.randrange(4)
        if choice == 0 and out:
            i = rng.randrange(len(out))
            out[i] ^= 1 << rng.randrange(8)
        elif choice == 1:
            i = rng.randrange(len(out) + 1)
            out.insert(i, rng.randrange(256))
        elif choice == 2 and out:
            del out[rng.randrange(len(out))]
        elif choice == 3 and out:
            i = rng.randrange(len(out))
            j = min(len(out), i + rng.randint(1, 8))
            out[i:i] = out[i:j]
    return bytes(out)


def _parse_oracles(rules):
    parsed = []
    for rule in rules:
        if rule.startswith("exit:"):
            parsed.append(("exit", int(rule.split(":", 1)[1])))
        elif rule.startswith("exit-not-in:"):
            values = {int(v) for v in rule.split(":", 1)[1].split(",") if v.strip()}
            parsed.append(("exit-not-in", values))
        elif rule.startswith("stdout-contains:"):
            parsed.append(("stdout-contains", rule.split(":", 1)[1]))
        elif rule.startswith("stderr-contains:"):
            parsed.append(("stderr-contains", rule.split(":", 1)[1]))
        elif rule == "timeout":
            parsed.append(("timeout", None))
        else:
            raise SystemExit("unknown oracle rule: %s" % rule)
    return parsed


def _matches(rules, rc, stdout, stderr, timed_out):
    hit = []
    for kind, value in rules:
        if kind == "timeout":
            if timed_out:
                hit.append("timeout")
        elif timed_out:
            continue
        elif kind == "exit":
            if rc != value:
                hit.append("exit:%d" % value)
        elif kind == "exit-not-in":
            if rc not in value:
                hit.append("exit-not-in:%s" % ",".join(str(v) for v in sorted(value)))
        elif kind == "stdout-contains":
            if value in stdout:
                hit.append("stdout-contains:%s" % value)
        elif kind == "stderr-contains":
            if value in stderr:
                hit.append("stderr-contains:%s" % value)
    return hit


def _git_commit(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    commit = r.stdout.strip()
    return commit if r.returncode == 0 and commit else None


def run_target(target, cwd, timeout, data):
    """Run one input; return (exit_code, stdout, stderr, timed_out, error)."""
    fd, path = tempfile.mkstemp(prefix="fuzz-input-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if "@INPUT@" in target:
            command = shlex.split(target.replace("@INPUT@", path))
        else:
            command = shlex.split(target) + [path]
        try:
            r = subprocess.run(command, cwd=cwd, input=data, timeout=timeout,
                               capture_output=True)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace")
            err = (e.stderr or b"").decode("utf-8", "replace")
            return None, out, err, True, None
        except FileNotFoundError as e:
            return None, "", "", False, str(e)
        return (r.returncode,
                r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"), False, None)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="Deterministic fuzz adapter")
    ap.add_argument("--target", required=True,
                    help="command template; @INPUT@ is replaced by the input path")
    ap.add_argument("--corpus", required=True, help="seed corpus directory")
    ap.add_argument("--record", required=True, help="path of the JSON run record")
    ap.add_argument("--findings-dir", default=None,
                    help="directory for failing inputs and logs "
                         "(default: <record without .json>-findings)")
    ap.add_argument("--runs", type=int, default=100,
                    help="number of mutated executions after the seed corpus (default 100)")
    ap.add_argument("--seed", type=int, default=0, help="fixed RNG seed")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="per-execution timeout in seconds (default 10)")
    ap.add_argument("--oracle", action="append", default=None,
                    help="oracle rule; repeatable (default: exit:0)")
    ap.add_argument("--max-findings", type=int, default=10,
                    help="stop after this many findings (default 10)")
    ap.add_argument("--cwd", default=None, help="working directory for the target")
    ap.add_argument("--commit", default=None,
                    help="commit under test (default: git HEAD of --cwd)")
    args = ap.parse_args()

    if args.runs < 0:
        print("--runs must be >= 0", file=sys.stderr)
        return 2
    if args.max_findings < 1:
        print("--max-findings must be >= 1", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be > 0", file=sys.stderr)
        return 2

    try:
        manifest, blobs = load_corpus(args.corpus)
        oracles = _parse_oracles(args.oracle or ["exit:0"])
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2

    cwd = args.cwd or os.getcwd()
    if not os.path.isdir(cwd):
        print("cwd not found: %s" % cwd, file=sys.stderr)
        return 2

    findings_dir = args.findings_dir
    if findings_dir is None:
        base = args.record[:-5] if args.record.endswith(".json") else args.record
        findings_dir = base + "-findings"
    os.makedirs(findings_dir, exist_ok=True)
    record_dir = os.path.dirname(os.path.abspath(args.record))
    os.makedirs(record_dir, exist_ok=True)

    corpus_root_abs = os.path.abspath(args.corpus)
    try:
        corpus_display = os.path.relpath(corpus_root_abs, cwd)
    except ValueError:
        corpus_display = corpus_root_abs
    rng = random.Random(args.seed)
    started_at = _now()
    digest = hashlib.sha256()
    findings = []
    executions = 0
    stopped_early = False
    target_error = None

    def execute(data, source):
        nonlocal executions, target_error, stopped_early
        rc, out, err, timed_out, error = run_target(
            args.target, cwd, args.timeout, data)
        if error:
            target_error = error
            return
        executions += 1
        input_hash = _sha256(data)
        digest.update(input_hash.encode())
        hits = _matches(oracles, rc, out, err, timed_out)
        if not hits:
            return
        combined = (out + "\n--- stderr ---\n" + err).encode("utf-8")
        input_path = os.path.join(findings_dir, input_hash + ".input")
        log_path = os.path.join(findings_dir, input_hash + ".log")
        if not os.path.exists(input_path):
            with open(input_path, "wb") as f:
                f.write(data)
        with open(log_path, "wb") as f:
            f.write(combined)
        findings.append({
            "input": os.path.relpath(input_path, record_dir).replace(os.sep, "/"),
            "input_sha256": input_hash,
            "input_size": len(data),
            "log": os.path.relpath(log_path, record_dir).replace(os.sep, "/"),
            "log_sha256": _sha256(combined),
            "oracle": hits,
            "exit_code": rc,
            "timed_out": timed_out,
            "seed_input": source,
        })
        if len(findings) >= args.max_findings:
            stopped_early = True

    for path, data in zip(manifest, blobs):
        execute(data, path["path"])
        if stopped_early:
            break
    if not stopped_early:
        for _ in range(args.runs):
            i = rng.randrange(len(blobs))
            execute(mutate(rng, blobs[i]), None)
            if stopped_early:
                break

    if target_error:
        print("cannot run target: %s" % target_error, file=sys.stderr)
        return 2

    record = {
        "tool": "fuzz_run.py",
        "version": SCHEMA_VERSION,
        "target": args.target,
        "cwd": cwd,
        "commit": args.commit or _git_commit(cwd),
        "seed": args.seed,
        "oracle": args.oracle or ["exit:0"],
        "corpus": {
            "path": corpus_display.replace(os.sep, "/"),
            "manifest": manifest,
        },
        "budget": {
            "runs": args.runs,
            "executions": executions,
            "timeout_seconds": args.timeout,
            "max_findings": args.max_findings,
            "stopped_early": stopped_early,
        },
        "started_at": started_at,
        "finished_at": _now(),
        "executions_digest": digest.hexdigest(),
        "findings": findings,
        "verdict": "findings" if findings else "clean",
    }
    with open(args.record, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=False)
        f.write("\n")

    print("fuzz: %s | executions: %d | findings: %d | seed: %d"
          % (args.record, executions, len(findings), args.seed))
    for item in findings:
        print("  %s  exit=%s oracle=%s" % (item["input_sha256"][:12],
                                           item["exit_code"], ",".join(item["oracle"])))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
