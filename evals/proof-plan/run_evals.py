#!/usr/bin/env python3
"""Adversarial eval runner for tools/proof_plan.py (V2-29).

Each scenario builds a throw-away git repository with a base and a head commit,
writes a proof manifest and a tool_output record, and runs the planner. The
fixtures are synthetic: they prove the planner reacts to the named diff shapes
and that its gates fail closed, not that any real proof exists. At the time of
writing the repository has no `proven` claim, so no real proof was re-run.

Usage:
    python3 evals/proof-plan/run_evals.py [--tool PATH]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

BASE_DATE = "2026-11-01T00:00:00 +0000"
HEAD_DATE = "2026-11-02T00:00:00 +0000"
OLD_RECORD = "2026-11-01T12:00:00+00:00"
NEW_RECORD = "2026-11-03T00:00:00+00:00"


def _write(root, rel, content, as_json=False):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if content is None:
        if os.path.exists(path):
            os.remove(path)
        return
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        elif as_json:
            json.dump(content, f, indent=2)
            f.write("\n")
        else:
            yaml.safe_dump(content, f, allow_unicode=True, sort_keys=False)


def _git(root, *argv, env=None):
    proc = subprocess.run(["git", "-C", root] + list(argv),
                          capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})))
    if proc.returncode != 0:
        raise RuntimeError("git %s: %s"
                           % (" ".join(argv), proc.stderr.strip()))
    return proc.stdout


def _init(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "eval@example.invalid")
    _git(root, "config", "user.name", "eval")
    _git(root, "config", "commit.gpgsign", "false")


def _commit(root, message, date):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", message,
         env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})


def _proof(pid="P-01", claim="C-34", artifact="proofs/P1.tla",
           record="proofs/P1.json", depends=("src/code.py",), model=(),
           encoding=(), tooling=(),
           assumptions=("The model abstracts the guard, not the SQL layer.",)):
    entry = {
        "id": pid,
        "claim": claim,
        "artifact": artifact,
        "tool_output": record,
        "depends_on": list(depends),
        "assumptions": list(assumptions),
    }
    if model:
        entry["model"] = list(model)
    if encoding:
        entry["encoding"] = list(encoding)
    if tooling:
        entry["tooling"] = list(tooling)
    return entry


def _manifest(*proofs):
    return {"version": 1, "proofs": list(proofs)}


def _record(path="proofs/P1.json", status="completed", finished=OLD_RECORD):
    return {"path": path, "content": {
        "tool": "TLC", "command": "java -jar tla2tools.jar P1.tla",
        "output": "proofs/P1.log", "output_sha256": "0" * 64,
        "exit_code": 0, "started_at": "2026-11-01T11:59:00+00:00",
        "finished_at": finished, "status": status,
    }}


BASE_FILES = {
    "src/code.py": "def guard():\n    return True\n",
    "src/other.py": "value = 1\n",
    "proofs/P1.tla": "---- MODULE P1 ----\n====\n",
    "proofs/P1.cfg": "SPECIFICATION Spec\n",
    "tools/encoder.py": "# encoder\n",
    "docs/README.md": "docs\n",
}

SCENARIOS = [
    {
        "name": "no-change-fresh",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "fresh"},
                   "summary": {"rerun": 0, "fresh": 1}},
    },
    {
        "name": "dependency-changed-stale",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {
            "exit": 0, "statuses": {"P-01": "rerun"},
            "reasons": {"P-01": ["dependency-changed",
                                 "record-predates-change"]},
            "summary": {"rerun": 1, "fresh": 0},
        },
    },
    {
        "name": "dependency-changed-covered",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished=NEW_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {
            "exit": 0, "statuses": {"P-01": "fresh"},
            "reasons": {"P-01": ["dependency-changed",
                                 "record-covers-change"]},
        },
    },
    {
        "name": "model-changed-stale",
        "head": {"proofs/P1.tla": "---- MODULE P1 ----\nEXTENDS Naturals\n====\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["dependency-changed",
                                        "record-predates-change"]}},
    },
    {
        "name": "encoding-changed-stale",
        "head": {"proofs/P1.cfg": "SPECIFICATION Spec\nCONSTANTS N = 2\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof(encoding=("proofs/P1.cfg",))),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"}},
    },
    {
        "name": "tooling-changed-stale",
        "head": {"tools/encoder.py": "# encoder, changed\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof(tooling=("tools/encoder.py",))),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"}},
    },
    {
        "name": "renamed-dependency-stale",
        "rename": ("src/code.py", "src/core.py"),
        "head": {},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "changed_statuses": ["R100"]},
    },
    {
        "name": "deleted-dependency-stale",
        "head": {"src/code.py": None},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "changed_statuses": ["D"]},
    },
    {
        "name": "manifest-changed-reruns",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record(finished=NEW_RECORD)],
        "manifest": _manifest(_proof(
            assumptions=("The model abstracts the guard only.",))),
        "manifest_base": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["manifest-changed"]}},
    },
    {
        "name": "proof-added-reruns",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record(),
                    _record("proofs/P2.json", finished=NEW_RECORD)],
        "manifest": _manifest(
            _proof(),
            _proof("P-02", "C-35", artifact="proofs/P2.tla",
                   record="proofs/P2.json")),
        "extra_files": {"proofs/P2.tla": "---- MODULE P2 ----\n====\n"},
        "manifest_base": _manifest(_proof()),
        "expect": {"exit": 0,
                   "statuses": {"P-01": "fresh", "P-02": "rerun"},
                   "reasons": {"P-02": ["proof-added"]}},
    },
    {
        "name": "all-forces-rerun",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record(finished=NEW_RECORD)],
        "manifest": _manifest(_proof()),
        "args": ["--all"],
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["all"]}},
    },
    {
        "name": "record-not-completed-reruns",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(status="unverified", finished=NEW_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["dependency-changed",
                                        "record-not-completed"]}},
    },
    {
        "name": "failed-record-no-change-reruns",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record(status="failed", finished=NEW_RECORD)],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["record-not-completed"]},
                   "summary": {"rerun": 1, "fresh": 0}},
    },
    {
        "name": "record-without-status-reruns",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [{"path": "proofs/P1.json",
                     "content": {"tool": "TLC", "exit_code": 0,
                                 "finished_at": NEW_RECORD}}],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["record-not-completed"]}},
    },
    {
        "name": "record-without-finished-at-reruns",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [{"path": "proofs/P1.json",
                     "content": {"tool": "TLC", "status": "completed",
                                 "exit_code": 0}}],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"},
                   "reasons": {"P-01": ["dependency-changed",
                                        "record-predates-change"]}},
    },
    {
        "name": "record-timestamp-equal-is-fresh",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished="2026-11-02T00:00:00+00:00")],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "statuses": {"P-01": "fresh"},
                   "reasons": {"P-01": ["dependency-changed",
                                        "record-covers-change"]}},
    },
    {
        "name": "require-fresh-blocks-stale",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof()),
        "args": ["--require-fresh"],
        "expect": {"exit": 1, "statuses": {"P-01": "rerun"}},
    },
    {
        "name": "require-fresh-allows-covered",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished=NEW_RECORD)],
        "manifest": _manifest(_proof()),
        "args": ["--require-fresh"],
        "expect": {"exit": 0, "statuses": {"P-01": "fresh"}},
    },
    {
        "name": "unmapped-material-reported",
        "head": {"proofs/Other.tla": "---- MODULE Other ----\n====\n"},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 0, "unmapped": ["proofs/Other.tla"],
                   "summary": {"unmapped": 1}},
    },
    {
        "name": "require-complete-blocks-unmapped",
        "head": {"proofs/Other.tla": "---- MODULE Other ----\n====\n"},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "args": ["--require-complete"],
        "expect": {"exit": 1, "unmapped": ["proofs/Other.tla"]},
    },
    {
        "name": "renamed-proof-material-reports-gap",
        "rename": ("proofs/Other.tla", "proofs/other.txt"),
        "extra_files": {"proofs/Other.tla": "---- MODULE Other ----\n====\n"},
        "head": {},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "args": ["--require-complete"],
        "expect": {"exit": 1, "unmapped": ["proofs/other.txt"],
                   "changed_statuses": ["R100"]},
    },
    {
        "name": "deleted-proof-material-reports-gap",
        "extra_files": {"proofs/Other.tla": "---- MODULE Other ----\n====\n"},
        "head": {"proofs/Other.tla": None},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "args": ["--require-complete"],
        "expect": {"exit": 1, "unmapped": ["proofs/Other.tla"],
                   "changed_statuses": ["D"]},
    },
    {
        "name": "removed-proof-reported",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "manifest_base": _manifest(
            _proof(), _proof("P-02", "C-35", artifact="proofs/P2.tla",
                             record="proofs/P2.json")),
        "expect": {"exit": 0, "removed": ["P-02"]},
    },
    {
        "name": "missing-record-is-input-error",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [],
        "manifest": _manifest(_proof()),
        "expect": {"exit": 2},
    },
    {
        "name": "missing-artifact-is-input-error",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof(artifact="proofs/absent.tla")),
        "expect": {"exit": 2},
    },
    {
        "name": "empty-depends-on-rejected",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof(depends=())),
        "expect": {"exit": 2},
    },
    {
        "name": "no-assumptions-rejected",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof(assumptions=())),
        "expect": {"exit": 2},
    },
    {
        "name": "unknown-entry-key-rejected",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        # A typo in depends_on must fail closed: ignoring it would delete the
        # only trigger and the proof would never re-run.
        "manifest": _manifest(dict(_proof(), depend_on=["src/code.py"])),
        "expect": {"exit": 2},
    },
    {
        "name": "unknown-top-level-key-rejected",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": dict(_manifest(_proof()), proof=[]),
        "expect": {"exit": 2},
    },
    {
        "name": "duplicate-id-rejected",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof(), _proof()),
        "expect": {"exit": 2},
    },
    {
        "name": "unknown-base-is-input-error",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [_record()],
        "manifest": _manifest(_proof()),
        "args": ["--base", "no-such-ref"],
        "expect": {"exit": 2},
    },
    {
        "name": "double-star-glob",
        "head": {"src/a/b.py": "x = 1\n"},
        "records": [_record(finished=OLD_RECORD)],
        "manifest": _manifest(_proof(depends=("src/**/*.py",))),
        "expect": {"exit": 0, "statuses": {"P-01": "rerun"}},
    },
    {
        "name": "two-proofs-partial",
        "head": {"src/code.py": "def guard():\n    return False\n"},
        "records": [_record(finished=OLD_RECORD),
                    _record("proofs/P2.json", finished=NEW_RECORD)],
        "manifest": _manifest(
            _proof(),
            _proof("P-02", "C-35", artifact="proofs/P2.tla",
                   record="proofs/P2.json", depends=("src/other.py",))),
        "extra_files": {"proofs/P2.tla": "---- MODULE P2 ----\n====\n"},
        "expect": {"exit": 0,
                   "statuses": {"P-01": "rerun", "P-02": "fresh"},
                   "summary": {"rerun": 1, "fresh": 1}},
    },
    {
        "name": "empty-manifest-is-honest",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [],
        "manifest": _manifest(),
        "expect": {"exit": 0, "statuses": {}, "summary": {"proofs": 0}},
    },
    {
        "name": "empty-manifest-gate-is-vacuous",
        "head": {"docs/README.md": "docs, edited\n"},
        "records": [],
        "manifest": _manifest(),
        "args": ["--require-fresh"],
        "expect": {"exit": 0,
                   "stdout_contains": ["no proofs are declared"]},
    },
    {
        "name": "empty-manifest-completeness-still-blocks",
        "head": {"proofs/Other.tla": "---- MODULE Other ----\n====\n"},
        "records": [],
        "manifest": _manifest(),
        "args": ["--require-complete"],
        "expect": {"exit": 1, "unmapped": ["proofs/Other.tla"]},
    },
]


def _run(args, td):
    return subprocess.run([sys.executable, args.tool] + args.argv, cwd=td,
                          capture_output=True, text=True, timeout=60)


def run(scenario, tool):
    problems = []
    td = tempfile.mkdtemp(prefix="proof-plan-eval-")
    try:
        _init(td)
        files = dict(BASE_FILES)
        files.update(scenario.get("extra_files") or {})
        for rel, content in files.items():
            _write(td, rel, content)
        records = scenario.get("records") or []
        for item in records:
            _write(td, item["path"], item["content"], as_json=True)
        _write(td, "manifest.yaml", scenario["manifest"])
        _commit(td, "base", BASE_DATE)

        head = scenario.get("head") or {}
        for rel, content in head.items():
            _write(td, rel, content)
        rename = scenario.get("rename")
        if rename:
            os.rename(os.path.join(td, rename[0]), os.path.join(td, rename[1]))
        _commit(td, "head", HEAD_DATE)

        if scenario.get("manifest_base") is not None:
            _write(td, "manifest-base.yaml", scenario["manifest_base"])

        argv = ["--repo", td, "--base", "HEAD~1", "--head", "HEAD",
                "--manifest", os.path.join(td, "manifest.yaml")]
        if scenario.get("manifest_base") is not None:
            argv += ["--manifest-base", os.path.join(td, "manifest-base.yaml")]
        argv += ["--json", os.path.join(td, "plan.json")]
        argv += scenario.get("args") or []
        proc = subprocess.run([sys.executable, tool] + argv, cwd=td,
                              capture_output=True, text=True, timeout=60)
        expect = scenario.get("expect") or {}
        if proc.returncode != expect.get("exit"):
            problems.append("exit: expected %s, got %d (stderr: %s)"
                            % (expect.get("exit"), proc.returncode,
                               proc.stderr.strip()[:300]))
        for needle in expect.get("stdout_contains") or []:
            if needle not in proc.stdout:
                problems.append("stdout: missing %r in %r"
                                % (needle, proc.stdout.strip()[:300]))
        plan_path = os.path.join(td, "plan.json")
        plan = None
        if os.path.exists(plan_path):
            with open(plan_path, encoding="utf-8") as f:
                plan = json.load(f)
        if plan is None:
            if expect.get("exit") != 2:
                problems.append("plan JSON was not written")
            return scenario["name"], problems

        statuses = {p["id"]: p["status"] for p in plan["proofs"]}
        if expect.get("statuses") is not None and statuses != expect["statuses"]:
            problems.append("statuses: expected %s, got %s"
                            % (expect["statuses"], statuses))
        for pid, kinds in (expect.get("reasons") or {}).items():
            got = [r["kind"] for r in next(
                p for p in plan["proofs"] if p["id"] == pid)["reasons"]]
            if got != kinds:
                problems.append("reasons %s: expected %s, got %s"
                                % (pid, kinds, got))
        removed = sorted(p["id"] for p in plan.get("removed") or [])
        if expect.get("removed") is not None and removed != expect["removed"]:
            problems.append("removed: expected %s, got %s"
                            % (expect["removed"], removed))
        unmapped = sorted(p["path"] for p in
                          plan.get("unmapped_proof_material") or [])
        if expect.get("unmapped") is not None and unmapped != expect["unmapped"]:
            problems.append("unmapped: expected %s, got %s"
                            % (expect["unmapped"], unmapped))
        for key, wanted in (expect.get("summary") or {}).items():
            got = (plan.get("summary") or {}).get(key)
            if got != wanted:
                problems.append("summary %s: expected %r, got %r"
                                % (key, wanted, got))
        if expect.get("changed_statuses") is not None:
            got = sorted(item["status"] for item in plan["changed_files"])
            if got != sorted(expect["changed_statuses"]):
                problems.append("changed statuses: expected %s, got %s"
                                % (expect["changed_statuses"], got))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return scenario["name"], problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "proof_plan.py"))
    args = ap.parse_args()
    failed = 0
    for scenario in SCENARIOS:
        name, problems = run(scenario, args.tool)
        if problems:
            failed += 1
            print("FAIL %s" % name)
            for problem in problems:
                print("     %s" % problem)
        else:
            print("ok   %s" % name)
    print("%d/%d proof-plan eval cases passed"
          % (len(SCENARIOS) - failed, len(SCENARIOS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
