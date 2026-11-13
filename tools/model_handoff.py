#!/usr/bin/env python3
"""Step 7: collect everything a reviewer needs into one folder.

The handoff folder is the unit we take back. It contains the artifacts, both
journal channels and the metrics, and a ``handoff.json`` that hashes every
file. ``--validate`` re-checks that manifest offline.

Layout (one folder per project; attempts live inside):

    <handoff>/
      README.txt          handoff.json       JOURNAL.md
      journal/<ts>/       metrics/           artifacts/
      target.json

The agent journal is required. A folder without ``JOURNAL.md`` is refused:
events prove a run happened, the journal explains why it looked like that, and
neither replaces the other.

Exit codes: 0 ok, 1 a gate failed (missing journal, invalid manifest, hash
mismatch), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

import yaml

from model_primitives import (
    FORMAT_HANDOFF, ModelError, journal_crash, load_json, now_iso,
    sha256_file, tool_block, validate_instance,
)

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(HERE), "spec", "models",
                      "handoff.schema.json")

ARTIFACTS = (
    "env.json",
    "inventory.json",
    "primitives.yaml",
    "decisions.yaml",
    "review.md",
    "review-index.json",
    "MODEL.md",
    "bounds.yaml",
    "generated/model.json",
    "generated/model.sys",
    "checks/results.json",
)

REVIEW_DIR = "review"


def _run_version(command):
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return (done.stdout or done.stderr).strip().splitlines()[0]


def environment() -> dict:
    tools = {}
    for name, command in (("rustc", ["rustc", "--version"]),
                          ("cargo", ["cargo", "--version"]),
                          ("git", ["git", "--version"])):
        path = shutil.which(name)
        tools[name] = {"present": bool(path), "path": path,
                       "version": _run_version(command) if path else None}
    probcli = shutil.which("probcli")
    tools["probcli"] = {"present": bool(probcli), "path": probcli,
                        "version": None}
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "yaml": getattr(yaml, "__version__", None),
        "tools": tools,
        "spec": spec_inputs(),
    }


# Spec files the gates consume. Their hashes go into env.json so a reviewer
# can verify the run judged against the same cells and traps, not just the
# same file names: "identical for everyone" is a checked fact, not an
# assumption (the stale-input class from Iteration 3).
SPEC_FILES = (
    "spec/traps.yaml",
    "spec/conveyor/cells.seed.yaml",
    "spec/invariants/catalog.yaml",
)


def spec_inputs() -> dict:
    import hashlib
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    commit = _run_version(["git", "-C", here, "rev-parse", "HEAD"])
    files = {}
    for rel in SPEC_FILES:
        path = os.path.join(here, rel)
        if not os.path.isfile(path):
            continue
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        files[rel] = digest.hexdigest()
    return {"git_commit": commit, "files": files}


def copy_artifacts(out: str, handoff: str, env: dict) -> list:
    target_dir = os.path.join(handoff, "artifacts")
    os.makedirs(target_dir, exist_ok=True)
    copied = []
    for name in ARTIFACTS:
        source = os.path.join(out, name)
        if not os.path.isfile(source):
            continue
        destination = os.path.join(target_dir, name)
        if os.path.isfile(destination) and os.path.samefile(source, destination):
            # MODEL_OUT may be <handoff>/artifacts itself; copying a file onto
            # itself is a crash, and there is nothing to copy.
            copied.append(name)
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(name)
    with open(os.path.join(target_dir, "env.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(env, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    if "env.json" not in copied:
        copied.append("env.json")
    source_review = os.path.join(out, REVIEW_DIR)
    if os.path.isdir(source_review):
        target_review = os.path.join(target_dir, REVIEW_DIR)
        if not (os.path.isdir(target_review)
                and os.path.samefile(source_review, target_review)):
            # MODEL_OUT may be <handoff>/artifacts itself; copying a directory
            # onto itself is a crash, and there is nothing to copy.
            shutil.copytree(source_review, target_review, dirs_exist_ok=True)
        copied.append(REVIEW_DIR + "/")
    return copied


def copy_runs(out: str, handoff: str) -> list:
    source = os.path.join(out, "runs")
    if not os.path.isdir(source):
        return []
    destination = os.path.join(handoff, "journal")
    os.makedirs(destination, exist_ok=True)
    runs = []
    for name in sorted(os.listdir(source)):
        run_dir = os.path.join(source, name)
        if not os.path.isdir(run_dir):
            continue
        target_dir = os.path.join(destination, name)
        inside = os.path.commonpath([os.path.abspath(run_dir),
                                     os.path.abspath(handoff)]) \
            == os.path.abspath(handoff)
        if inside:
            # MODEL_OUT lives inside the handoff folder: the run logs are
            # already hashed where they are; copying would duplicate them.
            events = os.path.join(run_dir, "events.jsonl")
            runs.append({
                "run_id": name,
                "path": os.path.relpath(events, handoff).replace(os.sep, "/"),
                "sha256": sha256_file(events) if os.path.isfile(events) else None,
            })
            continue
        shutil.copytree(run_dir, target_dir, dirs_exist_ok=True)
        events = os.path.join(target_dir, "events.jsonl")
        runs.append({
            "run_id": name,
            "path": os.path.join("journal", name, "events.jsonl"),
            "sha256": sha256_file(events) if os.path.isfile(events) else None,
        })
    return runs


def read_events(out: str) -> list:
    events = []
    source = os.path.join(out, "runs")
    if not os.path.isdir(source):
        return events
    for name in sorted(os.listdir(source)):
        path = os.path.join(source, name, "events.jsonl")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def build_metrics(events: list, primitives: dict, checks: dict) -> tuple:
    rows = []
    for event in events:
        rows.append({
            "ts": event.get("ts"),
            "run_id": event.get("run_id"),
            "step": event.get("step"),
            "exit": event.get("exit"),
            "status": event.get("status"),
            "duration_ms": event.get("duration_ms"),
            "target_commit": event.get("target_commit"),
            "target_dirty": event.get("target_dirty"),
            "counts": event.get("counts") or {},
            "error": event.get("error"),
        })

    by_step = {}
    for row in rows:
        by_step.setdefault(row["step"], []).append(row)

    primitives_counts = primitives.get("counts") or {}
    check_counts = checks.get("counts") or {}
    decisions = primitives.get("decisions") or []
    decision_by_id = {entry.get("id"): entry for entry in decisions
                      if isinstance(entry, dict)}
    approved = sum(1 for entry in decisions
                   if entry.get("decision") == "approved")
    total_decided = sum(1 for entry in decisions if entry.get("decision"))

    # Guard coverage counts only the operations that entered the model. An
    # operation is covered by a syntactic guard, or by an explicit
    # `no_guard_ok` that carries a note naming the enforcement point. The raw
    # count of operations with no syntactic guard stays in `check_counts`.
    mut_self = 0
    covered = 0
    for operation in primitives.get("operations") or []:
        if not operation.get("mut_self"):
            continue
        entry = decision_by_id.get(operation.get("id")) or {}
        if entry.get("decision") != "approved":
            continue
        mut_self += 1
        if operation.get("guards") or (entry.get("no_guard_ok")
                                       and entry.get("note")):
            covered += 1
    unmapped = primitives_counts.get("unmapped") or 0
    primitives_total = (primitives_counts.get("entities", 0)
                        + primitives_counts.get("state", 0)
                        + primitives_counts.get("operations", 0)
                        + primitives_counts.get("invariants", 0))
    anchors = check_counts.get("anchors") or 0
    stale = check_counts.get("stale") or 0
    vacuity = check_counts.get("vacuity_hits") or 0
    theorems = primitives_counts.get("invariants") or 0

    def ratio(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    summary = {
        "steps": len(rows),
        "failures": sum(1 for row in rows if row.get("exit") not in (0, None)),
        "iterations": len({row["run_id"] for row in rows}),
        "guard_coverage": ratio(covered, mut_self),
        "unmapped_share": ratio(unmapped, primitives_total + unmapped),
        "stale_share": ratio(stale, anchors),
        "vacuity_per_100_theorems": round(100.0 * vacuity / theorems, 2)
        if theorems else None,
        "approval_share": ratio(approved, total_decided),
        "median_step_ms": int(statistics.median(
            [row["duration_ms"] for row in rows
             if isinstance(row["duration_ms"], (int, float))]))
        if rows else None,
        # The handoff step writes its own event after these numbers are
        # derived, so it cannot appear in its own metrics.
        "excluded_steps": ["handoff"],
        "by_step": {
            step: {
                "runs": len(entries),
                "failures": sum(1 for entry in entries
                                if entry.get("exit") not in (0, None)),
                "median_ms": int(statistics.median(
                    [entry["duration_ms"] for entry in entries
                     if isinstance(entry["duration_ms"], (int, float))]))
                if entries else None,
            }
            for step, entries in sorted(by_step.items())
        },
    }

    lines = ["# Metrics", "",
             "Derived from `journal/*/events.jsonl`; nothing here is typed by "
             "hand.", "",
             "The `handoff` step appends its own event after these numbers are "
             "derived, so that invocation is not in the counts below; earlier "
             "handoff runs, if any, are.", "",
             "| Step | Runs | Failures | Median ms |",
             "| --- | --- | --- | --- |"]
    for step, entry in summary["by_step"].items():
        lines.append("| `%s` | %d | %d | %s |"
                     % (step, entry["runs"], entry["failures"],
                        entry["median_ms"] if entry["median_ms"] is not None
                        else "—"))
    lines += ["", "## Ratios", "",
              "| Ratio | Value | Meaning |",
              "| --- | --- | --- |",
              "| guard coverage | %s | `&mut self` operations with a guard, "
              "or an explicit no-guard-ok |" % _fmt(summary["guard_coverage"]),
              "| unmapped share | %s | share of extraction slots the extractor "
              "refused to guess |" % _fmt(summary["unmapped_share"]),
              "| stale share | %s | anchors whose snippet changed |"
              % _fmt(summary["stale_share"]),
              "| vacuity per 100 theorems | %s | guards that can never hold |"
              % _fmt(summary["vacuity_per_100_theorems"]),
              "| approval share | %s | decisions that are `approved` |"
              % _fmt(summary["approval_share"]),
              "", "## Raw counts (from the primitives artifact)", ""]
    for key in sorted(primitives_counts):
        lines.append("- `%s`: %s" % (key, primitives_counts[key]))
    lines.append("")
    return rows, summary, "\n".join(lines)


def _fmt(value):
    return "—" if value is None else str(value)


def open_questions(primitives, checks, decisions) -> list:
    questions = []
    counts = (checks or {}).get("counts") or {}
    if counts.get("stale"):
        questions.append("%d anchor(s) are stale: the code changed after "
                         "extraction" % counts["stale"])
    if counts.get("undecided"):
        questions.append("%d primitive(s) have no decision"
                         % counts["undecided"])
    # An operation without a syntactic guard is answered by the decision that
    # carries `no_guard_ok` and a note. Only the unexplained ones are open.
    by_id = {entry.get("id"): entry
             for entry in (decisions or {}).get("decisions") or []
             if isinstance(entry, dict)}
    unexplained = []
    for operation in primitives.get("operations") or []:
        if not operation.get("mut_self"):
            continue
        entry = by_id.get(operation.get("id")) or {}
        if entry.get("decision") != "approved":
            continue
        if operation.get("guards"):
            continue
        if entry.get("no_guard_ok") and entry.get("note"):
            continue
        unexplained.append(operation.get("id"))
    if unexplained:
        questions.append("%d `&mut self` operation(s) have no guard and no "
                         "`no_guard_ok` note: %s"
                         % (len(unexplained), ", ".join(unexplained)))
    if counts.get("vacuity_hits"):
        questions.append("%d guard(s) look vacuous"
                         % counts["vacuity_hits"])
    unmapped = len(primitives.get("unmapped") or [])
    if unmapped:
        questions.append("%d construct(s) are unmapped: the extractor refused "
                         "to guess" % unmapped)
    for entry in (decisions or {}).get("decisions") or []:
        if entry.get("decision") == "deferred":
            questions.append("deferred: %s — %s"
                             % (entry.get("id"), entry.get("note") or "no note"))
    return questions


def write_readme(handoff: str, project: str, handoff_json: dict) -> None:
    text = """\
Model handoff: {project}
=========================

This folder is self-contained. Read `handoff.json` first; it hashes every file
listed here.

  JOURNAL.md          the agent's account: intent, commands, facts, surprises
  journal/<ts>/       tool-written events and console output, one dir per run
  metrics/            metrics.jsonl (one line per step) and summary.md
  artifacts/          primitives, decisions, review, MODEL.md, generated model,
                      check results, environment
  target.json         path, commit, dirty flag and file count

Status: {status}
Anchors: {anchors} (stale {stale}, missing {missing})
Open questions: {questions}

Nothing here contains the target's source text. An anchor is a path, a line
range and a SHA-256 of the snippet, so the folder can be moved or committed
without copying someone else's code.

If a step is missing, say so in JOURNAL.md rather than filling it in here.
""".format(project=project,
           status=handoff_json.get("status"),
           anchors=handoff_json.get("counts", {}).get("anchors", 0),
           stale=handoff_json.get("counts", {}).get("stale", 0),
           missing=handoff_json.get("counts", {}).get("missing", 0),
           questions=len(handoff_json.get("open_questions") or []))
    with open(os.path.join(handoff, "README.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def hash_tree(root: str) -> list:
    entries = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ("__pycache__",))
        for name in sorted(files):
            if base == root and name == "handoff.json":
                continue
            full = os.path.join(base, name)
            relative = os.path.relpath(full, root)
            entries.append({"path": relative.replace(os.sep, "/"),
                            "sha256": sha256_file(full),
                            "bytes": os.path.getsize(full)})
    return entries


def validate(handoff_dir: str) -> list:
    path = os.path.join(handoff_dir, "handoff.json")
    if not os.path.isfile(path):
        return ["handoff.json is missing"]
    try:
        data = load_json(path)
        schema = load_json(SCHEMA)
    except (OSError, json.JSONDecodeError) as exc:
        return ["cannot read handoff.json: %s" % exc]
    errors = validate_instance(data, schema, where="handoff.json")
    for entry in data.get("artifacts") or []:
        full = os.path.join(handoff_dir, entry.get("path", ""))
        if not os.path.isfile(full):
            errors.append("artifact missing: %s" % entry.get("path"))
            continue
        if sha256_file(full) != entry.get("sha256"):
            errors.append("artifact hash mismatch: %s" % entry.get("path"))
    journal = data.get("journal") or {}
    agent = journal.get("agent_journal") or {}
    if not agent.get("present"):
        errors.append("JOURNAL.md is missing: the agent channel is required")
    elif not os.path.isfile(os.path.join(handoff_dir, "JOURNAL.md")):
        errors.append("handoff.json names JOURNAL.md but the file is absent")
    return errors


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Collect artifacts, journal and metrics into one folder.")
    ap.add_argument("--validate", default=None,
                    help="validate an existing handoff folder and exit")
    ap.add_argument("--target", default=None, help="Rust project")
    ap.add_argument("--out", default=None, help="artifact directory")
    ap.add_argument("--handoff", default=None, help="handoff folder")
    args = ap.parse_args(argv)

    if args.validate:
        errors = validate(os.path.abspath(args.validate))
        for error in errors:
            print("handoff: %s" % error)
        print("handoff: %s" % ("valid" if not errors else
                               "%d error(s)" % len(errors)))
        return 0 if not errors else 1

    if not args.target:
        ap.error("--target is required unless --validate is used")
    started = time.time()
    from model_primitives import prepare
    info, out, console, journal = prepare(args, "handoff")
    try:
        primitives_path = os.path.join(out, "primitives.yaml")
        model_path = os.path.join(out, "generated", "model.json")
        checks_path = os.path.join(out, "checks", "results.json")
        for path in (primitives_path, model_path, checks_path):
            if not os.path.isfile(path):
                raise ModelError("missing %s; finish the earlier steps first"
                                 % os.path.relpath(path, out))

        primitives = yaml.safe_load(open(primitives_path, encoding="utf-8"))
        checks = load_json(checks_path)
        decisions_path = os.path.join(out, "decisions.yaml")
        decisions = yaml.safe_load(open(decisions_path, encoding="utf-8")) \
            if os.path.isfile(decisions_path) else {}
        primitives_with_decisions = dict(primitives)
        primitives_with_decisions["decisions"] = decisions.get("decisions") or []

        if args.handoff:
            handoff = args.handoff
        elif os.environ.get("MODEL_HANDOFF_DIR"):
            handoff = os.path.join(os.environ["MODEL_HANDOFF_DIR"],
                                   info["name"])
        else:
            handoff = os.path.join(info["path"], ".model-handoff", info["name"])
            console("handoff: MODEL_HANDOFF_DIR is not set; writing inside the "
                    "target at %s" % handoff)
        handoff = os.path.abspath(os.path.expanduser(handoff))
        os.makedirs(handoff, exist_ok=True)

        env = environment()
        copy_artifacts(out, handoff, env)

        events = read_events(out)
        metrics_rows, summary, summary_text = build_metrics(
            events, primitives_with_decisions, checks)
        metrics_dir = os.path.join(handoff, "metrics")
        os.makedirs(metrics_dir, exist_ok=True)
        with open(os.path.join(metrics_dir, "metrics.jsonl"), "w",
                  encoding="utf-8", newline="\n") as fh:
            for row in metrics_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with open(os.path.join(metrics_dir, "summary.md"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(summary_text + "\n")

        agent_journal = os.path.join(handoff, "JOURNAL.md")
        source_journal = os.path.join(out, "JOURNAL.md")
        if not os.path.isfile(agent_journal) and os.path.isfile(source_journal):
            shutil.copy2(source_journal, agent_journal)
        journal_present = os.path.isfile(agent_journal)

        target_path = os.path.join(handoff, "target.json")
        with open(target_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"target": info,
                       "inventory": os.path.join("artifacts",
                                                 "inventory.json")},
                      fh, ensure_ascii=False, indent=2)
            fh.write("\n")

        payload = {
            "format": FORMAT_HANDOFF,
            "generated": now_iso(),
            "project": info["name"],
            "tool": tool_block("model_handoff"),
            "target": info,
            "environment": env,
            "status": checks.get("status", "open"),
            "counts": checks.get("counts") or {},
            "bounds": checks.get("bounds") or {"declared": False,
                                               "enumerated": False},
            "artifacts": hash_tree(handoff),
            "journal": {
                "runs": [],
                "agent_journal": {
                    "present": journal_present,
                    "path": "JOURNAL.md",
                    "sha256": sha256_file(agent_journal)
                    if journal_present else None,
                },
            },
            "metrics": {
                "path": os.path.join("metrics", "metrics.jsonl"),
                "sha256": sha256_file(os.path.join(metrics_dir,
                                                   "metrics.jsonl")),
                "lines": len(metrics_rows),
                "summary": summary,
            },
            "open_questions": open_questions(primitives_with_decisions,
                                             checks, decisions),
            "limitations": checks.get("limitations") or [],
        }
        handoff_path = os.path.join(handoff, "handoff.json")

        def write_manifest():
            # Copy the run logs first: copying appends to events.jsonl, so
            # hashing before the copy would record a hash the folder no longer
            # matches.
            payload["journal"]["runs"] = copy_runs(out, handoff)
            payload["artifacts"] = hash_tree(handoff)
            with open(handoff_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

        # README first, then hash: the manifest must cover the final README,
        # not the one from the previous attempt.
        write_readme(handoff, info["name"], payload)
        write_manifest()
        errors = validate(handoff)

        console("handoff: %s" % handoff)
        console("  files      %d" % len(payload["artifacts"]))
        console("  runs       %d" % len(payload["journal"]["runs"]))
        console("  metrics    %d line(s)" % len(metrics_rows))
        console("  status     %s" % payload["status"])
        console("  journal    %s" % ("present" if journal_present
                                    else "MISSING"))
        for error in errors:
            console("  ! %s" % error)

        # The event records the outcome of the work. It is written after the
        # checks, so the exit code and the log cannot disagree.
        journal.write(
            argv=sys.argv[1:], target=info["path"],
            target_commit=info["commit"], dirty=info["dirty"],
            exit_code=1 if errors else 0,
            duration_ms=int((time.time() - started) * 1000),
            outputs=[{"path": handoff_path,
                      "sha256": sha256_file(handoff_path)}],
            counts={"files": len(payload["artifacts"]),
                    "runs": len(payload["journal"]["runs"]),
                    "metrics_lines": len(metrics_rows)},
            status="error" if errors else "ok",
            error="; ".join(errors) if errors else None,
        )
        # Mechanism, not a second opinion: bring the event into the folder and
        # re-hash. If that breaks the manifest, the tool is at fault.
        write_manifest()
        final = validate(handoff)
        if final and not errors:
            console("  ! internal: the manifest stopped matching after "
                    "recording the event: %s" % "; ".join(final))
            return 2

        if errors:
            print("handoff: %d error(s); the folder is not ready" % len(errors))
            return 1
        print("handoff: %s" % handoff)
        return 0
    except ModelError as exc:
        console("handoff: %s" % exc)
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
