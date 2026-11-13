#!/usr/bin/env python3
"""Preflight and self-test for the code-to-model conveyor.

`model-doctor` answers one question: can this checkout produce a handoff that a
reviewer could trust, and do the gates actually refuse bad input? It does not
trust the pipeline's own claim. It:

* checks the prerequisites (Python, PyYAML, git, every tool, every schema);
* copies the `rust-tiny` fixture into a throwaway directory and runs every step
  through the real command line, exactly as an agent would;
* replaces the review checklist with the fixture's oracle decisions, then
  asserts the counts, the status and the artifact contents against it;
* validates every artifact against its schema and validates the handoff
  manifest offline;
* proves that the bounds file is handled honestly: a valid `bounds.yaml` is
  recorded as declared but not enumerated, and bounds without a `rationale`
  are refused;
* proves that a crash outside ``ModelError`` still leaves a journal event and
  that ``MODEL_OUT == <handoff>/artifacts`` does not crash the handoff;
* proves that the gates can fail: a tampered snippet must turn `check` red, a
  missing `no_guard_ok` must fail coverage, and a handoff without the agent
  journal must be refused. Each negative test restores the state and requires
  the pipeline to go green again, so a "failure" cannot be a stuck red.

What a green run proves: the tools run, their arithmetic matches the fixture
(including an operation with no body), the anchors resolve, the schemas accept
the artifacts, the bounds file is validated, a crash is still journaled, and
three named gates reject three specific violations. What it does not prove:
that the extractor understands Rust in general (the fixture is small and
authored here), that the generated B is consistent, or that any status above
`tested` is deserved.

Exit codes: 0 green, 1 a check failed, 2 the environment is not ready or the
doctor hit an internal error.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE = os.path.join(REPO, "spec", "fixtures", "rust-tiny")
SCHEMAS = os.path.join(REPO, "spec", "models")

TOOLS = (
    "model_init.py", "model_scan.py", "model_extract.py", "model_review.py",
    "model_gen.py", "model_check.py", "model_report.py", "model_handoff.py",
    "model_primitives.py", "rust_lexer.py", "rust_items.py",
)

SCHEMA_FILES = ("primitives.schema.json", "decisions.schema.json",
                "handoff.schema.json")

# The fixture is the oracle. These numbers are what extraction must produce;
# a change in any of them is a regression in the extractor or the fixture, and
# either way the doctor should stop.
EXPECT_SCAN = {
    "files": 2, "files_ok": 2, "files_failed": 0, "lines": 97,
    "structs": 1, "enums": 1, "impls": 1, "fns": 10, "pub_fns": 6,
    "mut_self_fns": 4,
}
EXPECT_EXTRACT = {
    "entities": 2, "state": 4, "operations": 10, "mut_self_ops": 4,
    "guards": 4, "effects": 9, "invariants": 5, "unmapped": 0,
}
EXPECT_CHECK = {
    "stale": 0, "missing": 0, "undecided": 0, "unguarded_mut_self": 2,
    "vacuity_hits": 0, "tautologies": 0, "dead_state": 2,
}
EXPECT_METRICS = {
    "failures": 0,
    "guard_coverage": 1.0,
    "unmapped_share": 0.0,
    "stale_share": 0.0,
    "vacuity_per_100_theorems": 0.0,
    "approval_share": 1.0,
}


class DoctorFailure(Exception):
    """A check the doctor refuses to pass; the message says which and why."""


class EnvironmentFailure(Exception):
    """The checkout cannot run the pipeline at all: exit 2, not a red gate."""


class Doctor:
    def __init__(self, workdir: str, keep: bool):
        self.workdir = workdir
        self.keep = keep
        self.target = os.path.join(workdir, "rust-tiny")
        self.out = os.path.join(workdir, "model")
        self.handoff = os.path.join(workdir, "handoff")
        self.run_label = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H-%M-%SZ") + "-doctor"
        self.steps = 0

    # -- plumbing ---------------------------------------------------------

    def say(self, message: str) -> None:
        print(message)

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise DoctorFailure(message)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise EnvironmentFailure(message)

    def run(self, tool: str, args, expect_rc=0, label=""):
        command = [sys.executable, os.path.join(HERE, tool)] + list(args)
        env = dict(os.environ)
        env["MODEL_RUN_ID"] = self.run_label
        done = subprocess.run(command, capture_output=True, text=True,
                              timeout=600, env=env)
        self.steps += 1
        tail = (done.stdout or "").strip().splitlines()
        summary = tail[-1] if tail else (done.stderr or "").strip()[:200]
        self.say("    %-14s exit %d  %s" % (label or tool, done.returncode,
                                            summary))
        if expect_rc is not None and done.returncode != expect_rc:
            raise DoctorFailure(
                "%s exited %d, expected %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
                % (tool, done.returncode, expect_rc, done.stdout, done.stderr))
        return done

    def path(self, *parts) -> str:
        return os.path.join(self.out, *parts)

    # -- preflight --------------------------------------------------------

    def preflight(self) -> None:
        self.say("preflight")
        self.require(sys.version_info >= (3, 11),
                     "Python 3.11+ is required, found %s"
                     % sys.version.split()[0])
        try:
            import yaml  # noqa: F401
        except ImportError:
            raise EnvironmentFailure("PyYAML is not installed: "
                                     "python3 -m pip install pyyaml")
        for name in ("git",):
            if shutil.which(name) is None:
                raise EnvironmentFailure("%s is not on PATH" % name)
        for tool in TOOLS:
            full = os.path.join(HERE, tool)
            self.require(os.path.isfile(full), "missing tool: %s" % full)
        for name in SCHEMA_FILES:
            full = os.path.join(SCHEMAS, name)
            self.require(os.path.isfile(full), "missing schema: %s" % full)
            self.check_json(full)
        self.require(os.path.isfile(os.path.join(FIXTURE, "src", "lib.rs")),
                     "fixture source is missing: %s" % FIXTURE)
        self.require(os.path.isfile(os.path.join(FIXTURE, "expected",
                                                 "decisions.yaml")),
                     "fixture oracle is missing: expected/decisions.yaml")
        self.say("  python %s, PyYAML ok, git ok, %d tools, %d schemas"
                 % (sys.version.split()[0], len(TOOLS), len(SCHEMA_FILES)))

    @staticmethod
    def check_json(path: str) -> None:
        import json
        try:
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)
        except (OSError, ValueError) as exc:
            raise EnvironmentFailure("%s is not valid JSON: %s" % (path, exc))

    # -- fixture ----------------------------------------------------------

    def prepare_target(self) -> None:
        self.say("fixture")
        self.expect(not os.path.exists(self.target),
                    "%s already exists; use an empty directory" % self.target)
        shutil.copytree(FIXTURE, self.target)
        lib = os.path.join(self.target, "src", "lib.rs")
        self.expect(os.path.isfile(lib), "fixture copy has no src/lib.rs")
        self.say("  %s -> %s" % (FIXTURE, self.target))

    def oracle(self) -> dict:
        import yaml
        path = os.path.join(FIXTURE, "expected", "decisions.yaml")
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        decisions = data.get("decisions") or []
        self.expect(decisions, "the fixture oracle lists no decisions")
        out = {}
        for entry in decisions:
            self.expect(isinstance(entry, dict) and entry.get("id"),
                        "oracle entry without an id: %r" % (entry,))
            self.expect(entry["id"] not in out,
                        "duplicate id in the oracle: %s" % entry["id"])
            out[entry["id"]] = entry
        return out

    # -- the pipeline -----------------------------------------------------

    def pipeline(self) -> dict:
        self.say("pipeline")
        self.run("model_init.py", ["--target", self.target, "--out", self.out],
                 label="init")
        self.expect(os.path.isfile(self.path("JOURNAL.md")),
                    "model-init did not write JOURNAL.md")
        self.expect(os.path.isfile(self.path("bounds.yaml.example")),
                    "model-init did not write bounds.yaml.example")

        self.run("model_scan.py", ["--target", self.target, "--out", self.out],
                 label="scan")
        inventory = self.load_json(self.path("inventory.json"))
        self.compare(inventory.get("totals") or {}, EXPECT_SCAN, "scan totals")
        self.expect(inventory.get("cargo", {}).get("edition") == "2021",
                    "scan did not read the Cargo edition")

        self.run("model_extract.py",
                 ["--target", self.target, "--out", self.out], label="extract")
        primitives = self.load_yaml(self.path("primitives.yaml"))
        self.compare(primitives.get("counts") or {}, EXPECT_EXTRACT,
                     "extract counts")
        self.check_anchor_shape(primitives)
        bodyless = {op["id"]: op
                    for op in primitives.get("operations") or []
                    if op["id"] == "O-before_audit"}
        self.expect("O-before_audit" in bodyless,
                    "the fixture's bodyless trait method was not extracted; "
                    "the first real run crashed exactly here")
        op = bodyless["O-before_audit"]
        self.expect(op.get("guards") == [] and op.get("effects") == []
                    and op.get("calls") == [],
                    "a bodyless operation must carry empty collections, "
                    "got guards=%r effects=%r calls=%r"
                    % (op.get("guards"), op.get("effects"), op.get("calls")))

        self.run("model_review.py",
                 ["--target", self.target, "--out", self.out], label="review")
        review = self.path("review.md")
        self.expect(os.path.isfile(review), "review did not write review.md")
        with open(review, "r", encoding="utf-8") as fh:
            review_text = fh.read()
        for heading in ("## Entities", "## State", "## Operations",
                        "## Candidate invariants", "## Unmapped"):
            self.expect(heading in review_text, "review.md lacks %r" % heading)
        # Fixture identity: 16 = 7 tiered ops + 2 entities + 4 state + 3 doc.
        self.expect(
            "Reconciliation: 16 required decisions = 7 tiered operations "
            "(tiers below) + 2 entities + 4 state fields + 3 doc invariants."
            in review_text,
            "review.md does not reconcile the queue against the tier sum")
        # The review step carries the shipped known traps into review.md.
        for trap_heading in ("## Known traps", "### stale-target-artifact",
                             "### offline-i18n-english-only",
                             "### union-resolve-drops-imports",
                             "### env-dependent-fails"):
            self.expect(trap_heading in review_text,
                        "review.md lacks the trap heading %r" % trap_heading)
        self.check_review_artifacts(primitives)

        self.decide(primitives, self.oracle())
        self.validate_schema("decisions.yaml", "decisions.schema.json")

        self.run("model_gen.py", ["--target", self.target, "--out", self.out],
                 label="gen")
        model = self.load_json(self.path("generated", "model.json"))
        self.expect(model.get("machine") == "rust_tiny",
                    "unexpected machine name: %r" % model.get("machine"))
        self.expect(len(model.get("sets") or []) == 1,
                    "expected one enum set, got %d" % len(model.get("sets") or []))
        self.expect(len(model.get("variables") or []) == 3,
                    "expected 3 translated variables (String is skipped), "
                    "got %d" % len(model.get("variables") or []))
        self.expect(len(model.get("unknown_types") or []) == 1,
                    "expected exactly one unknown type (String)")
        excluded = model.get("excluded") or {}
        for bucket in ("proposed", "rejected", "deferred"):
            self.expect(not excluded.get(bucket),
                        "the model excluded ids into %r although the oracle "
                        "approved everything: %r" % (bucket, excluded.get(bucket)))
        self.expect(sorted(excluded.get("test") or []) == [
                        "I-O-a_test_at_the_boundary-helper_in_tests",
                        "O-a_test_at_the_boundary", "O-helper_in_tests"],
                    "test code must land in the test bucket: %r"
                    % excluded.get("test"))
        self.expect(sorted(excluded.get("not_required") or []) == [
                        "I-O-Permissions-grant-self-roles-len", "O-describe"],
                    "the private read-only op and the assert invariant must "
                    "be not_required: %r" % excluded.get("not_required"))
        by_id = {inv["id"]: inv for inv in model.get("invariants") or []}
        assert_inv = by_id.get("I-O-Permissions-grant-self-roles-len")
        self.expect(assert_inv is not None,
                    "the assert invariant is missing from the model")
        self.expect(assert_inv.get("decided_by") == "O-Permissions-grant",
                    "the assert invariant must record its group decision: %r"
                    % assert_inv.get("decided_by"))
        self.expect(model.get("counts", {}).get("group_decided") == 1,
                    "group_decided must count the assert invariant: %r"
                    % model.get("counts", {}).get("group_decided"))
        sys_path = self.path("generated", "model.sys")
        with open(sys_path, "r", encoding="utf-8") as fh:
            sys_text = fh.read()
        self.expect(sys_text.startswith("/* Generated by"),
                    "model.sys lacks its generated header")
        self.expect("This is a SKELETON" in sys_text,
                    "model.sys no longer says it is a skeleton")
        self.expect("MACHINE rust_tiny" in sys_text,
                    "model.sys lacks the machine clause")
        self.expect("BEGIN" in sys_text and "END" in sys_text,
                    "model.sys has no operation blocks")

        self.run("model_check.py",
                 ["--target", self.target, "--out", self.out,
                  "--environment", "offline"], label="check")
        checks = self.load_json(self.path("checks", "results.json"))
        self.compare(checks.get("counts") or {}, EXPECT_CHECK, "check counts")
        self.expect(checks.get("status") == "tested",
                    "check status is %r, expected tested" % checks.get("status"))
        by_id = {check["id"]: check for check in checks.get("checks") or []}
        for name in ("anchor", "coverage", "vacuity"):
            self.expect(by_id.get(name, {}).get("status") == "pass",
                        "mandatory check %s did not pass" % name)
        self.expect(by_id.get("dead_state", {}).get("status") == "warn",
                    "dead state should warn, not block")
        self.expect(by_id.get("theorem", {}).get("status") == "warn",
                    "the weak-scope theorem should warn, not block")
        self.expect((checks.get("bounds") or {}).get("enumerated") is False,
                    "V0 must record bounds as not enumerated")
        self.expect(not (checks.get("bounds") or {}).get("declared"),
                    "the fixture declares no bounds.yaml")
        self.expect(checks.get("format") == "dev-sec-skills/model-checks/1",
                    "unexpected checks format: %r" % checks.get("format"))
        self.expect(checks.get("environment") == "offline",
                    "the environment scope is mandatory: %r"
                    % checks.get("environment"))

        self.run("model_report.py",
                 ["--target", self.target, "--out", self.out], label="report")
        with open(self.path("MODEL.md"), "r", encoding="utf-8") as fh:
            report = fh.read()
        self.expect("| Status | **tested** |" in report,
                    "MODEL.md does not state the tested status")
        self.expect("| `missing` |" not in report,
                    "MODEL.md reports a missing artifact hash")
        for section in ("## 1. Status", "## 7. Machine verification",
                        "## 8. Excluded and unmapped", "## 10. Limitations"):
            self.expect(section in report, "MODEL.md lacks %r" % section)

        self.run("model_handoff.py",
                 ["--target", self.target, "--out", self.out,
                  "--handoff", self.handoff], label="handoff")
        return {"primitives": primitives, "model": model, "checks": checks,
                "inventory": inventory}

    def decide(self, primitives: dict, oracle: dict) -> None:
        """Replace the checklist with the oracle, and refuse id drift."""
        current = self.load_yaml(self.path("decisions.yaml"))
        entries = current.get("decisions") or []
        ids = [entry.get("id") for entry in entries]
        self.expect(len(ids) == len([i for i in ids if i]),
                    "review wrote a decision without an id")
        self.expect(len(set(ids)) == len(ids),
                    "review wrote duplicate decision ids")
        missing = sorted(set(ids) - set(oracle))
        extra = sorted(set(oracle) - set(ids))
        self.expect(not missing,
                    "the oracle has no decision for extracted id(s): %s"
                    % ", ".join(missing))
        self.expect(not extra,
                    "the oracle expects id(s) the extractor no longer "
                    "produces: %s" % ", ".join(extra))
        self.expect(all(entry.get("decision") in (None, "")
                        for entry in entries),
                    "review must start with undecided entries")
        current["decisions"] = [oracle[entry["id"]] for entry in entries]
        from model_primitives import dump_yaml
        dump_yaml(self.path("decisions.yaml"), current,
                  header="# Written by model-doctor from the fixture oracle.\n")
        self.say("    %-14s %d ids matched the oracle" % ("oracle", len(ids)))

    # -- assertions -------------------------------------------------------

    def compare(self, actual: dict, expected: dict, label: str) -> None:
        for key, value in expected.items():
            self.expect(actual.get(key) == value,
                        "%s: %s is %r, expected %r"
                        % (label, key, actual.get(key), value))

    def check_anchor_shape(self, primitives: dict) -> None:
        allowed = {"path", "start", "end", "sha256", "note"}
        seen = 0

        def visit(node, where):
            nonlocal seen
            if isinstance(node, dict):
                if {"path", "start", "end"} <= set(node):
                    seen += 1
                    unexpected = set(node) - allowed
                    self.expect(not unexpected,
                                "anchor at %s carries %s; anchors hold a path, "
                                "a line range and a hash, never source text"
                                % (where, ", ".join(sorted(unexpected))))
                    self.expect("sha256" in node,
                                "anchor at %s has no sha256" % where)
                for key, value in node.items():
                    visit(value, "%s.%s" % (where, key))
            elif isinstance(node, list):
                for index, entry in enumerate(node):
                    visit(entry, "%s[%d]" % (where, index))

        visit(primitives, "primitives")
        self.expect(seen >= 20, "only %d anchors found, expected at least 20"
                    % seen)

    def validate_schema(self, relative: str, schema_name) -> None:
        if schema_name is None:
            return
        from model_primitives import validate_instance
        instance = (self.load_yaml(self.path(relative))
                    if relative.endswith((".yaml", ".yml"))
                    else self.load_json(self.path(relative)))
        errors = validate_instance(instance,
                                  self.load_json(os.path.join(SCHEMAS,
                                                              schema_name)),
                                  where=relative)
        self.expect(not errors, "%s fails %s:\n  %s"
                    % (relative, schema_name, "\n  ".join(errors)))

    def check_no_source_text(self) -> None:
        """A whole contiguous body block must never appear in an artifact."""
        lib = os.path.join(self.target, "src", "lib.rs")
        with open(lib, "r", encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        start = next(index for index, line in enumerate(lines)
                     if "self.roles.len() >= self.max_roles" in line)
        end = next(index for index in range(start, len(lines))
                   if lines[index].strip() == "Ok(())")
        block = "\n".join(lines[start:end + 1])
        self.expect(len(block.split("\n")) >= 4,
                    "the probe block is too short to be meaningful")
        scanned = 0
        for root in (self.out, self.handoff):
            for base, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d != "runs"]
                for name in files:
                    full = os.path.join(base, name)
                    try:
                        with open(full, "r", encoding="utf-8") as fh:
                            text = fh.read()
                    except (UnicodeDecodeError, OSError):
                        continue
                    scanned += 1
                    self.expect(block not in text,
                                "%s contains a whole source block verbatim: "
                                "anchors must replace source text"
                                % os.path.relpath(full, self.workdir))
        self.expect(scanned > 5, "only %d artifact files were scanned" % scanned)
        self.say("  %d artifact files contain no verbatim source block" % scanned)

    def check_handoff(self, expected_failures=0,
                      with_handoff_step=False) -> dict:
        import json
        done = self.run("model_handoff.py", ["--validate", self.handoff],
                        label="validate")
        self.expect(done.stdout.strip().endswith("handoff: valid"),
                    "model-handoff --validate did not report valid")
        with open(os.path.join(self.handoff, "handoff.json"), "r",
                  encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.expect(manifest.get("status") == "tested",
                    "handoff status is %r" % manifest.get("status"))
        journal = manifest.get("journal") or {}
        self.expect((journal.get("agent_journal") or {}).get("present") is True,
                    "handoff does not record the agent journal")
        self.expect(os.path.isfile(os.path.join(self.handoff, "JOURNAL.md")),
                    "handoff folder has no JOURNAL.md")
        runs = journal.get("runs") or []
        self.expect(runs, "handoff records no tool runs")
        for run in runs:
            self.expect(os.path.isfile(os.path.join(self.handoff,
                                                    run.get("path", ""))),
                        "handoff names a missing event log: %r"
                        % run.get("path"))
        paths = {entry["path"] for entry in manifest.get("artifacts") or []}
        for expected in ("README.txt", "JOURNAL.md", "artifacts/MODEL.md",
                         "artifacts/primitives.yaml", "artifacts/decisions.yaml",
                         "artifacts/checks/results.json",
                         "metrics/metrics.jsonl", "metrics/summary.md",
                         "target.json"):
            self.expect(expected in paths,
                        "handoff manifest omits %s" % expected)
        self.expect(not any(path.startswith("runs/") for path in paths),
                    "handoff copied a relative runs/ path")
        metrics = manifest.get("metrics") or {}
        summary = metrics.get("summary") or {}
        expected = dict(EXPECT_METRICS)
        # The negative tests leave their own failed events behind; the last
        # handoff derives its metrics from them, so the count must match the
        # failures the doctor deliberately caused.
        expected["failures"] = expected_failures
        self.compare(summary, expected, "metrics")
        self.expect(metrics.get("lines", 0) >= 6,
                    "metrics lines is %r" % metrics.get("lines"))
        self.expect(summary.get("iterations") == 1,
                    "all steps should share the doctor run id")
        expected_steps = ["check", "extract", "gen", "init", "report",
                          "review", "scan"]
        if with_handoff_step:
            # A previously failed handoff left its event behind, so this run's
            # metrics see that earlier step. The successful handoff still
            # excludes itself.
            expected_steps.append("handoff")
        self.expect(sorted(summary.get("by_step") or {}) == sorted(
            expected_steps),
            "metrics cover %r" % sorted(summary.get("by_step") or {}))
        self.expect(summary.get("excluded_steps") == ["handoff"],
                    "metrics must say the handoff step is not counted")
        questions = manifest.get("open_questions") or []
        self.expect(questions == [],
                    "open questions are %r; the fixture's decisions resolve "
                    "every item" % questions)
        self.expect(manifest.get("bounds", {}).get("declared") is False,
                    "the fixture must not declare bounds")
        self.say("  handoff valid: %d artifacts, %d run log(s), %d metrics line(s)"
                 % (len(paths), len(runs), metrics.get("lines", 0)))
        return manifest

    def check_review_artifacts(self, primitives: dict) -> None:
        """The queue carries only required ids; test code stays outside."""
        import yaml
        with open(self.path("decisions.yaml"), "r", encoding="utf-8") as fh:
            decisions = yaml.safe_load(fh) or {}
        ids = {entry.get("id") for entry in decisions.get("decisions") or []}
        test_ids = {"O-helper_in_tests", "O-a_test_at_the_boundary",
                    "I-O-a_test_at_the_boundary-helper_in_tests"}
        self.expect(not (ids & test_ids),
                    "test code reached decisions.yaml: %r" % (ids & test_ids))
        self.expect("O-describe" not in ids,
                    "a private read-only op reached decisions.yaml")
        index = self.load_json(self.path("review-index.json"))
        self.expect(index.get("required") == len(ids),
                    "review-index required %r != %d decisions"
                    % (index.get("required"), len(ids)))
        self.expect(sorted((index.get("tiers") or {}).keys())
                    == ["guarded", "mut-self-unguarded", "public-unguarded"],
                    "review-index tiers are %r" % sorted(index.get("tiers")))
        # The queue is bigger than the tier sum; the difference is accounted
        # for: entities, state fields and doc invariants are not tiered.
        breakdown = index.get("breakdown") or {}
        self.expect(sorted(breakdown.keys()) == [
                        "doc_invariants", "entities", "state",
                        "tiered_operations"],
                    "review-index breakdown keys are %r"
                    % sorted(breakdown.keys()))
        self.expect(sum(breakdown.values()) == index.get("required"),
                    "breakdown %r does not reconcile to %d required"
                    % (breakdown, index.get("required")))
        self.expect(breakdown.get("tiered_operations")
                    == sum((index.get("tiers") or {}).values()),
                    "tiered_operations %r != the tier sum %r"
                    % (breakdown.get("tiered_operations"),
                       sum((index.get("tiers") or {}).values())))
        self.expect(sorted(index.get("traps") or []) == [
                        "env-dependent-fails", "offline-i18n-english-only",
                        "stale-target-artifact",
                        "union-resolve-drops-imports"],
                    "review-index traps are %r" % sorted(index.get("traps")))
        areas = os.listdir(os.path.join(self.out, "review"))
        self.expect(areas == ["src-lib.rs.md"],
                    "unexpected area files: %r" % areas)
        with open(os.path.join(self.out, "review", "src-lib.rs.md"),
                  "r", encoding="utf-8") as fh:
            area_text = fh.read()
        self.expect("## Assert invariants" in area_text,
                    "the area file lacks the assert invariant section")

    def check_review_queue(self) -> None:
        """--include-tests puts test code back into review.md, not decisions."""
        self.say("review queue: --include-tests must restore test code")
        self.run("model_review.py",
                 ["--target", self.target, "--out", self.out,
                  "--include-tests"], label="review(tests)")
        with open(self.path("review.md"), "r", encoding="utf-8") as fh:
            with_tests = fh.read()
        self.expect("O-helper_in_tests" in with_tests,
                    "--include-tests did not put the test op into review.md")
        import yaml
        with open(self.path("decisions.yaml"), "r", encoding="utf-8") as fh:
            decisions = yaml.safe_load(fh) or {}
        ids = {entry.get("id") for entry in decisions.get("decisions") or []}
        self.expect("O-helper_in_tests" not in ids,
                    "--include-tests added a test op to decisions.yaml; the "
                    "op is private and read-only, so it is not required")
        self.run("model_review.py",
                 ["--target", self.target, "--out", self.out],
                 label="review(restored)")
        with open(self.path("review.md"), "r", encoding="utf-8") as fh:
            restored = fh.read()
        self.expect("O-helper_in_tests" not in restored,
                    "the default review did not exclude test code again")

    # -- bounds -----------------------------------------------------------

    def check_bounds(self) -> None:
        """A declared bound is recorded, never promoted; a guess is refused."""
        self.say("bounds: a valid file is recorded but not enumerated")
        path = self.path("bounds.yaml")
        self.expect(not os.path.exists(path),
                    "the fixture already declares bounds.yaml")
        from model_primitives import dump_yaml
        valid = {
            "bounds": {
                "max_instances": 3,
                "max_depth": 4,
                "max_states": 10000,
                "rationale": "the doctor's own domain: three roles and three "
                             "users cover every branch, deeper explodes",
            },
        }
        dump_yaml(path, valid, header="# written by model-doctor\n")
        try:
            self.run("model_check.py",
                     ["--target", self.target, "--out", self.out,
                      "--environment", "offline"], label="check(bounds)")
            checks = self.load_json(self.path("checks", "results.json"))
            bounds = checks.get("bounds") or {}
            self.expect(bounds.get("declared") is True,
                        "check did not record the declared bounds")
            self.expect(bounds.get("enumerated") is False,
                        "V0 must never mark bounds as enumerated")
            self.expect((bounds.get("values") or {}).get("max_instances") == 3,
                        "check lost the bounds values: %r"
                        % bounds.get("values"))
            self.expect(checks.get("status") == "tested",
                        "valid bounds changed the status to %r"
                        % checks.get("status"))
            self.expect(any("bounds.yaml" in item and "enumerated" in item
                            for item in checks.get("limitations") or []),
                        "check did not say the bounds were not enumerated: %r"
                        % (checks.get("limitations") or []))
        finally:
            os.unlink(path)

        self.say("negative: bounds without a rationale must be refused")
        dump_yaml(path, {"bounds": {"max_instances": 3}})
        try:
            done = self.run(
                "model_check.py",
                ["--target", self.target, "--out", self.out,
                 "--environment", "offline"],
                expect_rc=2, label="check(bounds-no-rationale)")
            self.expect("rationale" in (done.stdout + done.stderr),
                        "check refused the bounds for an unrelated reason:\n%s"
                        % (done.stdout + done.stderr))
        finally:
            os.unlink(path)
        self.run("model_check.py",
                 ["--target", self.target, "--out", self.out,
                  "--environment", "offline"], label="check(bounds-restored)")

    # -- negative tests ---------------------------------------------------

    def negative_tampered_source(self) -> None:
        self.say("negative: a tampered snippet must turn check red")
        lib = os.path.join(self.target, "src", "lib.rs")
        with open(lib, "r", encoding="utf-8") as fh:
            original = fh.read()
        needle = "assert!(self.roles.len() <= self.max_roles);"
        self.expect(needle in original, "the tamper probe is no longer present")
        with open(lib, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(original.replace(needle, needle.replace(");", " + 1);")))
        try:
            self.run("model_check.py",
                     ["--target", self.target, "--out", self.out,
                      "--environment", "offline"],
                     expect_rc=1, label="check(tampered)")
            checks = self.load_json(self.path("checks", "results.json"))
            self.expect((checks.get("counts") or {}).get("stale", 0) >= 1,
                        "check did not count a stale anchor")
            self.expect(checks.get("status") != "tested",
                        "check passed a tampered snippet")
            anchor = next(check for check in checks["checks"]
                          if check["id"] == "anchor")
            self.expect(anchor["status"] == "fail",
                        "the anchor check did not fail")
        finally:
            with open(lib, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(original)
        self.run("model_check.py",
                 ["--target", self.target, "--out", self.out,
                  "--environment", "offline"], label="check(restored)")
        checks = self.load_json(self.path("checks", "results.json"))
        self.expect(checks.get("status") == "tested",
                    "check did not go green after the source was restored")

    def negative_missing_no_guard_ok(self) -> None:
        self.say("negative: dropping no_guard_ok must fail coverage")
        path = self.path("decisions.yaml")
        with open(path, "r", encoding="utf-8") as fh:
            original = fh.read()
        data = self.load_yaml(path)
        entry = next(entry for entry in data["decisions"]
                     if entry.get("id") == "O-Permissions-reset")
        entry.pop("no_guard_ok", None)
        from model_primitives import dump_yaml
        dump_yaml(path, data, header="# negative test\n")
        try:
            self.run("model_check.py",
                     ["--target", self.target, "--out", self.out,
                      "--environment", "offline"],
                     expect_rc=1, label="check(no-guard)")
            checks = self.load_json(self.path("checks", "results.json"))
            coverage = next(check for check in checks["checks"]
                            if check["id"] == "coverage")
            self.expect(coverage["status"] == "fail",
                        "coverage did not fail without no_guard_ok")
            self.expect(any("no_guard_ok" in item
                            for item in coverage.get("items") or []),
                        "coverage failed for the wrong reason: %r"
                        % coverage.get("items"))
            # A handoff is still collectable while the status is open; it must
            # carry the unresolved item as an open question, not hide it.
            self.run("model_handoff.py",
                     ["--target", self.target, "--out", self.out,
                      "--handoff", self.handoff], label="handoff(no-guard)")
            self.run("model_handoff.py", ["--validate", self.handoff],
                     label="validate(no-guard)")
            manifest = self.load_json(os.path.join(self.handoff,
                                                   "handoff.json"))
            self.expect(manifest.get("status") == "open",
                        "handoff status is %r, expected open"
                        % manifest.get("status"))
            questions = manifest.get("open_questions") or []
            self.expect(any("no_guard_ok" in question for question in questions),
                        "the unresolved operation is not an open question: %r"
                        % questions)
        finally:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(original)
        self.run("model_check.py",
                 ["--target", self.target, "--out", self.out,
                  "--environment", "offline"], label="check(restored)")
        checks = self.load_json(self.path("checks", "results.json"))
        self.expect(checks.get("status") == "tested",
                    "check did not go green after decisions were restored")
        self.run("model_handoff.py",
                 ["--target", self.target, "--out", self.out,
                  "--handoff", self.handoff], label="handoff(restored)")
        self.check_handoff(expected_failures=3, with_handoff_step=True)

    def negative_missing_journal(self) -> None:
        self.say("negative: a handoff without JOURNAL.md must be refused")
        in_handoff = os.path.join(self.handoff, "JOURNAL.md")
        in_out = self.path("JOURNAL.md")
        saved_handoff = in_handoff + ".saved"
        saved_out = in_out + ".saved"
        shutil.move(in_handoff, saved_handoff)
        shutil.move(in_out, saved_out)
        try:
            done = self.run("model_handoff.py",
                            ["--target", self.target, "--out", self.out,
                             "--handoff", self.handoff],
                            expect_rc=1, label="handoff(no-journal)")
            self.expect("JOURNAL" in (done.stdout + done.stderr),
                        "handoff refused for an unrelated reason:\n%s"
                        % (done.stdout + done.stderr))
            validate = self.run("model_handoff.py",
                                ["--validate", self.handoff], expect_rc=1,
                                label="validate(no-journal)")
            self.expect("JOURNAL.md is missing" in validate.stdout,
                        "the validator did not name the missing agent journal")
        finally:
            shutil.move(saved_handoff, in_handoff)
            shutil.move(saved_out, in_out)
        self.run("model_handoff.py",
                 ["--target", self.target, "--out", self.out,
                  "--handoff", self.handoff], label="handoff(restored)")
        # Four deliberately failed invocations are now in the event log: the
        # bounds check, two gate checks, and the refused handoff. `--validate`
        # writes no event.
        self.check_handoff(expected_failures=4, with_handoff_step=True)

    def negative_missing_traps(self) -> None:
        """A review without the shipped traps file must refuse, not skip."""
        self.say("negative: a review without the traps file must be refused")
        done = self.run("model_review.py",
                        ["--target", self.target, "--out", self.out,
                         "--traps", os.path.join(self.workdir, "no-traps.yaml")],
                        expect_rc=2, label="review(no-traps)")
        self.expect("traps file not found" in (done.stdout + done.stderr),
                    "review refused for an unrelated reason:\n%s"
                    % (done.stdout + done.stderr))
        self.run("model_review.py",
                 ["--target", self.target, "--out", self.out],
                 label="review(restored)")

    def check_handoff_samefile(self) -> None:
        """MODEL_OUT == <handoff>/artifacts must not crash the handoff."""
        self.say("handoff: MODEL_OUT inside the handoff folder must not crash")
        inline = os.path.join(self.workdir, "handoff-inline")
        os.makedirs(inline, exist_ok=True)
        moved = os.path.join(inline, "artifacts")
        shutil.move(self.out, moved)
        try:
            done = self.run("model_handoff.py",
                            ["--target", self.target, "--out", moved,
                             "--handoff", inline], label="handoff(inline)")
            self.expect("SameFileError" not in (done.stdout + done.stderr),
                        "handoff crashed on MODEL_OUT == <handoff>/artifacts")
            manifest = self.load_json(os.path.join(inline, "handoff.json"))
            self.expect(manifest.get("status") == "tested",
                        "inline handoff status is %r" % manifest.get("status"))
            runs = (manifest.get("journal") or {}).get("runs") or []
            self.expect(runs, "inline handoff records no tool runs")
            for run in runs:
                self.expect(os.path.isfile(os.path.join(inline,
                                                        run.get("path", ""))),
                            "inline handoff names a missing run log: %r"
                            % run.get("path"))
            self.expect(not any(run["path"].startswith("journal/")
                                for run in runs),
                        "inline handoff duplicated run logs into journal/: %r"
                        % [run["path"] for run in runs])
            paths = {entry["path"] for entry in manifest.get("artifacts") or []}
            for expected in ("artifacts/primitives.yaml",
                             "artifacts/checks/results.json",
                             "metrics/metrics.jsonl", "target.json",
                             "JOURNAL.md"):
                self.expect(expected in paths,
                            "inline handoff manifest omits %s" % expected)
        finally:
            shutil.move(moved, self.out)

    # -- driver -----------------------------------------------------------

    def load_json(self, path: str):
        import json
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def load_yaml(self, path: str):
        import yaml
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}


def main(argv) -> int:
    ap = argparse.ArgumentParser(
        description="Preflight and self-test the model conveyor.")
    ap.add_argument("--keep", action="store_true",
                    help="keep the throwaway directory even on success")
    ap.add_argument("--dir", default=None,
                    help="use this directory instead of a fresh temporary one")
    args = ap.parse_args(argv)

    if args.dir:
        workdir = os.path.abspath(args.dir)
        os.makedirs(workdir, exist_ok=True)
        disposable = False
    else:
        workdir = tempfile.mkdtemp(prefix="model-doctor-")
        disposable = True
    doctor = Doctor(workdir, args.keep)
    try:
        doctor.preflight()
        doctor.prepare_target()
        doctor.pipeline()
        doctor.check_no_source_text()
        doctor.check_handoff()
        doctor.check_bounds()
        doctor.negative_tampered_source()
        doctor.negative_missing_no_guard_ok()
        doctor.negative_missing_journal()
        doctor.negative_missing_traps()
        doctor.check_handoff_samefile()
        doctor.check_review_queue()
    except DoctorFailure as exc:
        print("\nmodel-doctor: FAILED\n  %s" % str(exc).replace("\n", "\n  "))
        print("\nwork directory kept for inspection: %s" % doctor.workdir)
        return 1
    except EnvironmentFailure as exc:
        print("\nmodel-doctor: NOT READY\n  %s"
              % str(exc).replace("\n", "\n  "))
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print("\nmodel-doctor: ERROR\n  %s: %s"
              % (type(exc).__name__, exc))
        print("\nwork directory kept for inspection: %s" % doctor.workdir)
        return 2
    if disposable and not args.keep:
        shutil.rmtree(doctor.workdir, ignore_errors=True)
    print("\nmodel-doctor: green")
    print("  %d tool invocations, fixture %s"
          % (doctor.steps, os.path.relpath(FIXTURE, REPO)))
    print("  proved: counts, anchors, schemas, bounds validation, handoff "
          "manifest, bodyless operations, crash journaling, inline "
          "MODEL_OUT, required-only queue, queue reconciliation, known "
          "traps in review, environment scope, and three gates that can "
          "fail")
    print("  not proved: general Rust coverage, B consistency, any status "
          "above tested")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
