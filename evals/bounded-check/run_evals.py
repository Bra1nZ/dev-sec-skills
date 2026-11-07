#!/usr/bin/env python3
"""Adversarial eval runner for tools/bounded_check.py (V2-28).

Each case runs a real child process through the supervisor and checks the
record it produced: exit code, `status`, `timed_out`, the captured log's bytes
and SHA-256, and — for the two integration cases — whether `claim_lint` reads
the record as support for a `model-checked` claim.

The child commands are synthetic fixtures (`python -c ...`), not checkers.
A passing run proves the supervisor classifies its own child faithfully and
that the linter refuses `unverified` for a non-open claim; it does not prove
that any real model checker is bounded correctly.

Usage:
    python3 evals/bounded-check/run_evals.py [--tool PATH]
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_TOOL = os.path.join(REPO, "tools", "bounded_check.py")
CLAIM_LINT = os.path.join(REPO, "tools", "claim_lint.py")

ALLOWED_KEYS = {
    "tool", "version", "command", "output", "output_sha256", "exit_code",
    "started_at", "finished_at", "verdict", "status", "timed_out",
    "bound_seconds", "elapsed_seconds", "bound",
}
REQUIRED_KEYS = {
    "tool", "command", "output", "output_sha256", "exit_code", "started_at",
    "finished_at", "status",
}


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _record_from(case, td, proc):
    if case.get("record_path"):
        path = os.path.join(td, case["record_path"])
        if not os.path.exists(path):
            return None, "record file was not written: %s" % case["record_path"]
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    try:
        return json.loads(proc.stdout), None
    except ValueError:
        return None, "stdout is not a JSON record: %r" % proc.stdout[:200]


def check_record(case, td, proc):
    problems = []
    expect = case["expect"]
    if proc.returncode != expect["exit"]:
        problems.append("exit: expected %s, got %d (stderr: %s)"
                        % (expect["exit"], proc.returncode,
                           proc.stderr.strip()[:300]))
    if not expect.get("record", True):
        if proc.stdout.strip():
            problems.append("stdout should stay empty on a usage error, got %r"
                            % proc.stdout[:200])
        return problems

    record, problem = _record_from(case, td, proc)
    if problem:
        problems.append(problem)
        return problems

    keys = set(record)
    if keys - ALLOWED_KEYS:
        problems.append("record has keys outside tool-output.schema.json: %s"
                        % sorted(keys - ALLOWED_KEYS))
    if REQUIRED_KEYS - keys:
        problems.append("record lacks required keys: %s"
                        % sorted(REQUIRED_KEYS - keys))

    for field in ("status", "timed_out", "exit_code"):
        if field in expect and record.get(field) != expect[field]:
            problems.append("%s: expected %r, got %r"
                            % (field, expect[field], record.get(field)))
    if expect.get("version") and record.get("version") != expect["version"]:
        problems.append("version: expected %r, got %r"
                        % (expect["version"], record.get("version")))
    if expect.get("bound") and record.get("bound") != expect["bound"]:
        problems.append("bound: expected %r, got %r"
                        % (expect["bound"], record.get("bound")))
    if expect.get("exit_negative") and not (isinstance(record.get("exit_code"), int)
                                            and record["exit_code"] < 0):
        problems.append("exit_code: expected a negative signal value, got %r"
                        % record.get("exit_code"))
    if expect.get("min_elapsed") is not None:
        if not record.get("elapsed_seconds", 0) >= expect["min_elapsed"]:
            problems.append("elapsed_seconds: expected >= %r, got %r"
                            % (expect["min_elapsed"],
                               record.get("elapsed_seconds")))
    if expect.get("max_elapsed") is not None:
        if not record.get("elapsed_seconds", 0) <= expect["max_elapsed"]:
            problems.append("elapsed_seconds: expected <= %r, got %r"
                            % (expect["max_elapsed"],
                               record.get("elapsed_seconds")))

    log_path = record.get("output")
    if log_path and os.path.isabs(log_path):
        if not os.path.exists(log_path):
            problems.append("captured log does not exist: %s" % log_path)
        else:
            digest = sha256_file(log_path)
            if digest != record.get("output_sha256"):
                problems.append("output_sha256 does not match the log")
            if "log" in expect:
                with open(log_path, encoding="utf-8") as f:
                    text = f.read()
                if text != expect["log"]:
                    problems.append("log: expected %r, got %r"
                                    % (expect["log"], text))
            if expect.get("log_empty") and os.path.getsize(log_path) != 0:
                problems.append("log: expected an empty capture")
    return problems


def run_simple(case, td, tool):
    argv = [sys.executable, tool] + case["build"](td)
    proc = subprocess.run(argv, capture_output=True, text=True,
                          timeout=120, cwd=td)
    problems = check_record(case, td, proc)
    if case.get("stdout_json") is False and proc.stdout.strip():
        problems.append("--json should keep stdout free of the record, got %r"
                        % proc.stdout[:120])
    if case.get("stderr_contains") and case["stderr_contains"] not in proc.stderr:
        problems.append("stderr does not contain %r" % case["stderr_contains"])
    return problems


def _ledger(record, status):
    from datetime import date
    try:
        day = record["finished_at"][:10]
    except KeyError:
        day = date.today().isoformat()
    return {
        "project": "bounded-check eval fixture",
        "claims": [{
            "id": "C-01",
            "claim": "The demo command answers within its wall-clock bound.",
            "mechanism": "tools/bounded_check.py supervises the process group.",
            "evidence": [{
                "kind": "model-check",
                "command": record["command"],
                "date": day,
                "tool_output": record,
            }],
            "scope": {
                "platforms": ["synthetic fixture"],
                "assumptions": ["The fixture command stands in for a checker."],
            },
            "status": status,
            "limitations": "A synthetic command; no checker semantics.",
        }],
    }


def run_claim_lint_case(case, td, tool):
    """Run the supervisor, embed its record in a ledger, and lint the ledger."""
    problems = []
    record_path = os.path.join(td, "record.json")
    argv = [sys.executable, tool] + case["build"](td)
    proc = subprocess.run(argv, capture_output=True, text=True,
                          timeout=120, cwd=td)
    if proc.returncode != case["expect"]["exit"]:
        problems.append("supervisor exit: expected %s, got %d"
                        % (case["expect"]["exit"], proc.returncode))
    if not os.path.exists(record_path):
        return problems + ["supervisor did not write the record"]
    with open(record_path, encoding="utf-8") as f:
        record = json.load(f)

    ledger_path = os.path.join(td, "ledger.yaml")
    with open(ledger_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(_ledger(record, case["expect"]["claim_status"]), f,
                       sort_keys=False)

    lint = subprocess.run(
        [sys.executable, CLAIM_LINT, "--root", td,
         "--tool-output-root", td, "--max-age-days", "3650",
         ledger_path],
        capture_output=True, text=True, timeout=120)
    if lint.returncode != case["expect"]["lint_exit"]:
        problems.append("claim_lint exit: expected %s, got %d\n%s"
                        % (case["expect"]["lint_exit"], lint.returncode,
                           lint.stdout.strip()[:400]))
    want_error = case["expect"].get("line2_error")
    has_error = any(line.strip().startswith("[L2] error")
                    for line in lint.stdout.splitlines())
    if want_error is not None and has_error != want_error:
        problems.append("claim_lint L2 error: expected %r, got %r\n%s"
                        % (want_error, has_error, lint.stdout.strip()[:400]))
    return problems


CASES = [
    {
        "name": "clean-control",
        "build": lambda td: [
            "--tool", "Demo", "--tool-version", "1.0", "--timeout", "10",
            "--output", os.path.join(td, "reports", "demo.log"),
            "--bound", "depth 8", "--",
            sys.executable, "-c",
            "import sys\n"
            "sys.stdout.write('out\\n'); sys.stdout.flush()\n"
            "sys.stderr.write('err\\n'); sys.stderr.flush()\n"
            "sys.stdout.write('more\\n'); sys.stdout.flush()\n",
        ],
        "expect": {
            "exit": 0, "status": "completed", "timed_out": False,
            "exit_code": 0, "version": "1.0", "bound": "depth 8",
            "log": "out\nerr\nmore\n", "min_elapsed": 0,
        },
    },
    {
        "name": "timeout-unverified",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "1",
            "--output", os.path.join(td, "sleep.log"), "--",
            sys.executable, "-c", "import time; time.sleep(30)",
        ],
        "expect": {
            "exit": 3, "status": "unverified", "timed_out": True,
            "exit_negative": True, "log_empty": True,
            "min_elapsed": 0.9, "max_elapsed": 20,
        },
    },
    {
        "name": "nonzero-failed",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "10",
            "--output", os.path.join(td, "fail.log"), "--",
            sys.executable, "-c",
            "import sys; print('boom'); sys.exit(3)",
        ],
        "expect": {
            "exit": 1, "status": "failed", "timed_out": False,
            "exit_code": 3, "log": "boom\n",
        },
    },
    {
        "name": "missing-binary-error",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "10",
            "--output", os.path.join(td, "missing.log"), "--",
            "definitely-not-a-real-checker-v2-28",
        ],
        "expect": {
            "exit": 2, "status": "error", "timed_out": False,
            "exit_code": 127, "log_empty": True,
        },
    },
    {
        "name": "timeout-zero-rejected",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "0",
            "--output", os.path.join(td, "never.log"),
            "--json", os.path.join(td, "never.json"), "--",
            sys.executable, "-c", "print('unreachable')",
        ],
        "expect": {"exit": 2, "record": False},
    },
    {
        "name": "empty-command-rejected",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "10",
            "--output", os.path.join(td, "never.log"),
            "--json", os.path.join(td, "never.json"), "--",
        ],
        "expect": {"exit": 2, "record": False},
    },
    {
        "name": "json-file-record",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "10",
            "--output", os.path.join(td, "ok.log"),
            "--json", "record.json", "--",
            sys.executable, "-c", "print('fine')",
        ],
        "record_path": "record.json",
        "expect": {
            "exit": 0, "status": "completed", "exit_code": 0,
            "log": "fine\n",
        },
        "stdout_json": False,
        "stderr_contains": "Demo completed",
    },
    {
        "name": "process-group-killed",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "1",
            "--output", os.path.join(td, "group.log"), "--",
            sys.executable, "-c",
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c',\n"
            "    'import time; time.sleep(60)'])\n"
            "open(sys.argv[1], 'w').write(str(child.pid))\n"
            "time.sleep(60)\n",
            os.path.join(td, "grandchild.pid"),
        ],
        "expect": {
            "exit": 3, "status": "unverified", "timed_out": True,
            "exit_negative": True, "min_elapsed": 0.9,
        },
        "group_kill": True,
    },
]

INTEGRATION_CASES = [
    {
        "name": "claim-lint-completed-supports",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "10", "--bound", "depth 8",
            "--output", os.path.join(td, "ok.log"),
            "--json", os.path.join(td, "record.json"), "--",
            sys.executable, "-c", "print('checked')",
        ],
        "expect": {
            "exit": 0, "claim_status": "model-checked", "lint_exit": 0,
            "line2_error": False,
        },
    },
    {
        "name": "claim-lint-unverified-blocks",
        "build": lambda td: [
            "--tool", "Demo", "--timeout", "1",
            "--output", os.path.join(td, "late.log"),
            "--json", os.path.join(td, "record.json"), "--",
            sys.executable, "-c", "import time; time.sleep(30)",
        ],
        "expect": {
            "exit": 3, "claim_status": "model-checked", "lint_exit": 1,
            "line2_error": True,
        },
    },
]


def _grandchild_gone(pid, deadline=5.0):
    """True once the pid no longer exists (a killed orphan may linger briefly)."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return True
        time.sleep(0.1)
    return False


def run(case, td, tool):
    if case.get("group_kill"):
        problems = run_simple(case, td, tool)
        pid_file = os.path.join(td, "grandchild.pid")
        if not os.path.exists(pid_file):
            return problems + ["grandchild pid file was not written"]
        pid = int(open(pid_file, encoding="utf-8").read().strip())
        if not _grandchild_gone(pid):
            problems.append("grandchild pid %d survived the process-group kill"
                            % pid)
        return problems
    if "claim_status" in case.get("expect", {}):
        return run_claim_lint_case(case, td, tool)
    return run_simple(case, td, tool)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=DEFAULT_TOOL)
    args = ap.parse_args()

    failed = 0
    total = len(CASES) + len(INTEGRATION_CASES)
    for case in CASES + INTEGRATION_CASES:
        td = tempfile.mkdtemp(prefix="bounded-check-eval-")
        try:
            problems = run(case, td, args.tool)
        finally:
            shutil.rmtree(td, ignore_errors=True)
        if problems:
            failed += 1
            print("FAIL %s" % case["name"])
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % case["name"])
    print("%d/%d bounded-check eval cases passed" % (total - failed, total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
