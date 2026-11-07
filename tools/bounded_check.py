#!/usr/bin/env python3
"""Run one external check under a wall-clock bound and record how it ended (V2-28).

A checker that hangs produces the same artifact as a checker that finished: a
model file, a log, a zero-length tail. The difference is not in the artifact,
it is in the supervision. This wrapper starts the tool in its own process
group, enforces a wall-clock bound, kills the whole group when the bound
elapses, and writes a `tool_output` record
(`schemas/tool-output.schema.json`) whose `status` says which of four things
happened:

  completed   the process exited before the bound; `exit_code` is its own
  unverified  the bound elapsed and the group was killed, or the tool reported
              that it could not decide; no conclusion follows
  failed      the process exited non-zero before the bound
  error       the wrapper could not start or supervise the process

`unverified` is the point of the tool. A timeout is not a pass with a short
log, and it is not a crash that loses the run: it is a recorded fact that
`claim_lint` refuses to read as support for a non-open claim.

What the record does NOT say:

- It does not paraphrase the tool. `verdict` is left to the tool's own result
  line in the captured log; a supervisor that invents a verdict is a second
  source of truth.
- It does not decide whether a non-zero exit is a failure or a negative
  verdict. A checker whose contract says "exit 1 = counterexample" needs an
  adapter that maps that exit to a verdict; here it is `failed`, which is the
  fail-closed default: a claim cannot rest on it, and a human reads the log.
- It does not prove the tool's semantics. A forger can rewrite the log and the
  hash together (C-13).

The captured log contains exactly the bytes the tool wrote to stdout and
stderr, in arrival order. The wrapper does not inject marker lines, so
`output_sha256` is a hash of the tool's output, not of the wrapper's story.

Exit codes: 0 completed, 1 failed, 2 usage or supervision error,
3 unverified (bound elapsed).

Usage:
    python3 tools/bounded_check.py \
        --tool TLC --tool-version 2.19 --timeout 900 \
        --output reports/tlc.log [--bound "depth 8"] [--json record.json] \
        -- java -jar tla2tools.jar -config AuthGate.cfg AuthGate.tla
"""

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime

EXIT_FOR_STATUS = {"completed": 0, "failed": 1, "error": 2, "unverified": 3}

# 127 is the shell convention for "command not found"; 126 for "found but not
# executable". Both are recorded so the log and the record agree on why the
# tool produced nothing.
EXIT_NOT_FOUND = 127
EXIT_NOT_EXECUTABLE = 126


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def write_json(path, record):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _kill_group(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # The group is already gone or the wrapper cannot signal it; the
        # wait below still reaps the direct child.
        pass


def run_bounded(command, timeout, output_path):
    """Run `command`; return a tool_output record and a wrapper-level note.

    The note is for the wrapper's own stderr and is never written into the
    captured log.
    """
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)
    started_at = now_iso()
    started = time.monotonic()
    note = None

    with open(output_path, "wb") as log:
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            note = "cannot start %r: %s" % (command[0], exc)
            status = "error"
            exit_code = (EXIT_NOT_FOUND if isinstance(exc, FileNotFoundError)
                         else EXIT_NOT_EXECUTABLE)
            timed_out = False
        else:
            try:
                exit_code = proc.wait(timeout=timeout)
                timed_out = False
                status = "completed" if exit_code == 0 else "failed"
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc)
                exit_code = proc.wait()
                status = "unverified"
                note = ("wall-clock bound %ds elapsed; process group killed"
                        % timeout)

    elapsed = time.monotonic() - started
    record = {
        "tool": None,  # filled by the caller
        "command": shlex.join(command),
        "output": output_path,
        "output_sha256": sha256_file(output_path),
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": now_iso(),
        "status": status,
        "timed_out": timed_out,
        "bound_seconds": timeout,
        "elapsed_seconds": round(elapsed, 3),
    }
    return record, note


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool", required=True,
                    help="tool name recorded in the tool_output record")
    ap.add_argument("--tool-version", dest="tool_version", default=None,
                    help="tool version; a verdict means little without it")
    ap.add_argument("--timeout", type=int, default=None,
                    help="wall-clock bound in seconds (integer >= 1)")
    ap.add_argument("--output", required=True,
                    help="path for the captured combined stdout/stderr")
    ap.add_argument("--json", default=None,
                    help="write the tool_output record here (default: stdout)")
    ap.add_argument("--bound", default=None,
                    help="state-space or depth bound, e.g. 'depth 8'")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="the command to supervise, after --")
    args = ap.parse_args(argv)

    if args.timeout is None or args.timeout < 1:
        ap.error("--timeout must be an integer >= 1")
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        ap.error("no command given; put it after --")
    if args.json and os.path.abspath(args.json) == os.path.abspath(args.output):
        ap.error("--json and --output must be different paths")
    if os.path.isdir(args.output):
        ap.error("--output is a directory: %s" % args.output)

    record, note = run_bounded(command, args.timeout, args.output)
    record["tool"] = args.tool
    if args.tool_version:
        record["version"] = args.tool_version
    if args.bound:
        record["bound"] = args.bound

    if args.json:
        try:
            write_json(args.json, record)
        except OSError as exc:
            print("bounded_check: cannot write %s: %s" % (args.json, exc),
                  file=sys.stderr)
            return EXIT_FOR_STATUS["error"]
    else:
        print(json.dumps(record, indent=2))

    print("bounded_check: %s %s in %.3fs; log %s"
          % (args.tool, record["status"], record["elapsed_seconds"],
             args.output), file=sys.stderr)
    if note:
        print("bounded_check: %s" % note, file=sys.stderr)
    return EXIT_FOR_STATUS[record["status"]]


if __name__ == "__main__":
    sys.exit(main())
