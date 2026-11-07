#!/usr/bin/env python3
"""Adversarial eval runner for tools/sarif_evidence.py (V2-23).

Each case builds a synthetic SARIF log, a synthetic registry and an adapter
config, runs the normalizer, and checks the exit code, the SARIF check that
fires, the unmapped reasons and the JSON summary. The fixtures are synthetic:
they prove the adapter fails closed on the named defects, not that any engine
produced a real finding.

Usage:
    python3 evals/sarif/run_evals.py [--tool PATH]
"""

import argparse
import copy
import json
import os
import re
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
SCHEMA = os.path.join(REPO, "spec", "conveyor", "cell-registry.schema.json")
ERROR_RE = re.compile(r"^\[(SARIF\d)\]\s+(error|warning|info)\b", re.M)

CATEGORIES = {"security": "invalid-or-injected-input",
              "correctness": "check-then-act"}


def _rule(engine_id, pattern, cell="demo/CELL-001", taxonomy="security",
          mode="deny"):
    return {
        "id": "%s-rule" % engine_id,
        "match": pattern,
        "taxonomy_class": taxonomy,
        "failure_class": "invalid-or-injected-input" if taxonomy == "security"
                         else "check-then-act",
        "failure_mode": mode,
        "cell": cell,
    }


def _config(rules=None, registries=None, engines=None):
    return {
        "version": 1,
        "registries": registries or {"demo": "cells.yaml"},
        "engines": engines or [
            {"id": "semgrep", "name": "Semgrep",
             "rules": rules or [_rule("semgrep", "^py/sql-injection$")]},
            {"id": "codeql", "name": "CodeQL",
             "rules": [_rule("codeql", "^py/command-line-injection$")]},
            {"id": "bandit", "name": "Bandit",
             "rules": [_rule("bandit", "^B608$")]},
        ],
    }


def _cells():
    return {"cells": [
        {"id": "CELL-001"}, {"id": "CELL-002"}]}


def _result(rule, path="src/app.py", start=10, end=None, fingerprint="fp-1",
            level="error", message="synthetic finding"):
    result = {
        "ruleId": rule,
        "level": level,
        "message": {"text": message},
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {"uri": path, "uriBaseId": "%SRCROOT%"},
                "region": {"startLine": start},
            }
        }],
    }
    if end is not None:
        result["locations"][0]["physicalLocation"]["region"]["endLine"] = end
    if fingerprint:
        result["partialFingerprints"] = {"primaryLocationLineHash": fingerprint}
    return result


def _sarif(engine, results, fixture=True):
    doc = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": engine, "version": "0.0.0-fixture",
                                "rules": []}},
            "results": results,
        }],
    }
    if fixture:
        doc["properties"] = {"dev-sec-skills/fixture": True}
    return doc


def _scenario(name, documents, expect, config=None, args=None):
    return {"name": name, "documents": documents, "config": config,
            "args": args, "expect": expect}


SCENARIOS = [
    _scenario("three-engines-mapped", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
        "codeql.sarif": _sarif("CodeQL", [
            _result("py/command-line-injection", fingerprint="c-1")]),
        "bandit.sarif": _sarif("Bandit", [
            _result("B608", path="app/db.py", fingerprint="b-1")]),
    }, {
        "exit": 0, "errors": [],
        "json": {"findings": 3, "unmapped": 0, "engines_present": 3,
                 "duplicates": 0, "fixture_inputs": 3},
        "paths": ["app/db.py", "src/app.py", "src/app.py"],
    }, args=["--max-unmapped", "0", "--require-engines", "3"]),

    _scenario("duplicate-fingerprint", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="same"),
            _result("py/sql-injection", fingerprint="same"),
            _result("py/sql-injection", path="src/other.py",
                    fingerprint="other")]),
    }, {
        "exit": 0, "errors": [],
        "json": {"findings": 2, "duplicates": 1, "unmapped": 0},
    }, args=["--max-unmapped", "0"]),

    _scenario("unknown-engine", {
        "other.sarif": _sarif("Invented", [
            _result("py/sql-injection", fingerprint="u-1")]),
    }, {
        "exit": 1, "errors": ["SARIF2"],
        "json": {"findings": 0, "unmapped": 1, "engines_present": 0},
        "reasons": ["unknown-engine"],
    }, args=["--max-unmapped", "0"]),

    _scenario("unmapped-rule", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("python.something-else", fingerprint="r-1")]),
    }, {
        "exit": 1, "errors": ["SARIF2"],
        "json": {"findings": 0, "unmapped": 1},
        "reasons": ["unmapped-rule"],
    }, args=["--max-unmapped", "0"]),

    _scenario("missing-location", {
        "semgrep.sarif": _sarif("Semgrep", [{
            "ruleId": "py/sql-injection",
            "level": "error",
            "message": {"text": "no location"},
        }]),
    }, {
        "exit": 1, "errors": ["SARIF2"],
        "json": {"findings": 0, "unmapped": 1},
        "reasons": ["missing-location"],
    }, args=["--max-unmapped", "0"]),

    _scenario("missing-rule-id", {
        "semgrep.sarif": _sarif("Semgrep", [{
            "level": "error",
            "message": {"text": "no rule"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "src/app.py"},
                "region": {"startLine": 1}}}],
        }]),
    }, {
        "exit": 1, "errors": ["SARIF2"],
        "json": {"findings": 0, "unmapped": 1},
        "reasons": ["missing-rule-id"],
    }, args=["--max-unmapped", "0"]),

    _scenario("bad-sarif-version", {
        "broken.sarif": {
            "$schema": "https://example.invalid/sarif.json",
            "version": "2.0.0",
            "runs": [],
        },
    }, {
        "exit": 1, "errors": ["SARIF1"], "json": {"findings": 0},
    }, args=["--max-unmapped", "0"]),

    _scenario("bad-json", {
        "broken.sarif": "{not json",
    }, {
        "exit": 1, "errors": ["SARIF1"], "json": {"findings": 0},
    }, args=["--max-unmapped", "0"]),

    _scenario("missing-input", {
        "semgrep.sarif": _sarif("Semgrep", []),
    }, {
        "exit": 1, "errors": ["SARIF1"], "json": {"findings": 0},
    }, args=["--max-unmapped", "0", "--input", "does-not-exist.sarif"]),

    _scenario("require-three-engines", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
    }, {
        "exit": 1, "errors": ["SARIF2"],
        "json": {"findings": 1, "engines_present": 1},
    }, args=["--max-unmapped", "0", "--require-engines", "3"]),

    _scenario("reject-fixtures", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
    }, {
        "exit": 1, "errors": ["SARIF1"],
        "json": {"fixture_inputs": 1},
    }, args=["--max-unmapped", "0", "--reject-fixtures"]),

    _scenario("unknown-cell-is-config-error", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
    }, {
        "exit": 2, "errors": ["SARIF3"],
    }, config=_config(rules=[
        _rule("semgrep", "^py/sql-injection$", cell="demo/CELL-999")])),

    _scenario("bad-taxonomy-is-config-error", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
    }, {
        "exit": 2, "errors": ["SARIF3"],
    }, config=_config(rules=[
        _rule("semgrep", "^py/sql-injection$", taxonomy="other")])),

    _scenario("file-uri-is-rebased", {
        "semgrep.sarif": None,  # filled with the temp root at run time
    }, {
        "exit": 0, "errors": [],
        "json": {"findings": 1, "unmapped": 0},
        "paths": ["src/app.py"],
    }, args=["--max-unmapped", "0"]),

    _scenario("stable-digest", {
        "semgrep.sarif": _sarif("Semgrep", [
            _result("py/sql-injection", fingerprint="s-1")]),
        "codeql.sarif": _sarif("CodeQL", [
            _result("py/command-line-injection", path="src/other.py",
                    fingerprint="c-1")]),
    }, {
        "exit": 0, "errors": [],
        "json": {"findings": 2},
        "digest_stable": True,
    }, args=["--max-unmapped", "0"]),
]


def _write(root, rel, content):
    path = os.path.join(root, rel)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        else:
            json.dump(content, f, indent=2)


def _dotted(data, key):
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return "<missing>"
    return node


def _run_once(tool, td, config_path, documents, args):
    inputs = []
    for rel in sorted(documents):
        inputs.append(os.path.join(td, rel))
    cmd = [sys.executable, tool, "--config", config_path, "--root", td]
    cmd += args + inputs
    report_path = os.path.join(td, "report.json")
    if "--json" not in args:
        cmd += ["--json", report_path]
    proc = subprocess.run(cmd, cwd=td, capture_output=True, text=True,
                          timeout=60)
    report = None
    if os.path.exists(report_path):
        report = json.load(open(report_path, encoding="utf-8"))
    return proc, report


def run(scenario, tool):
    problems = []
    td = tempfile.mkdtemp(prefix="sarif-eval-")
    try:
        _write(td, "cells.yaml", _cells())
        config = copy.deepcopy(scenario["config"] or _config())
        with open(os.path.join(td, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, sort_keys=False)
        documents = {}
        for rel, content in scenario["documents"].items():
            if content is None:
                content = _sarif("Semgrep", [_result(
                    "py/sql-injection",
                    path="file://" + os.path.join(td, "src/app.py"),
                    fingerprint="u-1")])
            documents[rel] = content
            _write(td, rel, content)

        args = list(scenario.get("args") or [])
        # `--input` is a convenience for the missing-input case; turn it into a
        # positional argument that does not exist.
        extra = []
        if "--input" in args:
            idx = args.index("--input")
            extra.append(args[idx + 1])
            del args[idx:idx + 2]
        inputs = [os.path.join(td, rel) for rel in sorted(documents)] + extra
        cmd = [sys.executable, tool, "--config", os.path.join(td, "config.yaml"),
               "--root", td] + args
        report_path = os.path.join(td, "report.json")
        cmd += ["--json", report_path] + inputs
        proc = subprocess.run(cmd, cwd=td, capture_output=True, text=True,
                              timeout=60)
        expect = scenario["expect"]
        if proc.returncode != expect.get("exit"):
            problems.append("exit: expected %s, got %d (%s)"
                            % (expect.get("exit"), proc.returncode,
                               proc.stderr.strip()[:300]))
        seen = sorted(set(ERROR_RE.findall(proc.stderr)))
        seen = [code for code, level in ERROR_RE.findall(proc.stderr)
                if level == "error"]
        if "errors" in expect and sorted(set(seen)) != sorted(expect["errors"]):
            problems.append("errors: expected %s, got %s"
                            % (expect["errors"], sorted(set(seen))))

        report = None
        if os.path.exists(report_path):
            report = json.load(open(report_path, encoding="utf-8"))
        if report is None and expect.get("json") is not None:
            problems.append("JSON report was not written")
        elif report is not None:
            for key, wanted in (expect.get("json") or {}).items():
                got = _dotted(report.get("summary", {}), key)
                if got != wanted:
                    problems.append("json %s: expected %r, got %r"
                                    % (key, wanted, got))
            if "reasons" in expect:
                got = sorted(item["reason"] for item in report.get("unmapped") or [])
                if got != sorted(expect["reasons"]):
                    problems.append("unmapped reasons: expected %s, got %s"
                                    % (expect["reasons"], got))
            if "paths" in expect:
                got = sorted(item["path"] for item in report.get("findings") or [])
                if got != sorted(expect["paths"]):
                    problems.append("paths: expected %s, got %s"
                                    % (expect["paths"], got))
            if expect.get("digest_stable"):
                order = list(sorted(documents))
                rev = list(reversed(order))
                inputs_rev = [os.path.join(td, rel) for rel in rev]
                cmd_rev = [sys.executable, tool, "--config",
                           os.path.join(td, "config.yaml"), "--root", td]
                cmd_rev += args + ["--json", os.path.join(td, "rev.json")] \
                    + inputs_rev
                proc_rev = subprocess.run(cmd_rev, cwd=td, capture_output=True,
                                          text=True, timeout=60)
                rev_report = json.load(open(os.path.join(td, "rev.json"),
                                            encoding="utf-8"))
                if proc_rev.returncode != 0:
                    problems.append("digest replay exited %d" % proc_rev.returncode)
                elif rev_report["summary"]["digest"] != report["summary"]["digest"]:
                    problems.append("digest changed when input order changed")
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return scenario["name"], problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default=os.path.join(REPO, "tools",
                                                   "sarif_evidence.py"))
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
    print("%d/%d SARIF eval cases passed"
          % (len(SCENARIOS) - failed, len(SCENARIOS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
