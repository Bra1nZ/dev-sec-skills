#!/usr/bin/env python3
"""Adversarial evals for the AI diff reviewer (tools/ai_review.py).
The canary case is the minimum trust precondition for the reviewer: a diff
with a planted, unambiguous vulnerability (command injection, hardcoded
credential, path traversal) must produce at least one high/medium finding
that cites the planted file. This is the same discipline as the
craft-i18n scan: a "0 findings" result proves nothing unless the reviewer
demonstrates it can see a known issue.

The control case is a clean diff: zero high findings is required; a
medium/low on clean code is recorded as a warning, not a failure (one-shot
LLM reviewers over-alert; that failure mode is measured, not hidden).

The eval calls the real model hub and needs ASTRA_API_KEY in the
environment. Without the key it exits 0 with a SKIP notice, so local
`make verify` and CI without the secret do not break; the PR review
workflow runs it as a preflight where the key exists.

Usage: python3 evals/ai-review/run_evals.py [--canary-only]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TOOLS = os.path.join(REPO, "tools", "ai_review.py")

FIXTURES = [
    {
        "name": "canary",
        "patch": os.path.join(HERE, "fixtures", "canary.patch"),
        "target": os.path.join(HERE, "fixtures", "canary_target.py"),
        "target_path": "tools/examples/stand_query.py",
        "mode": "hard",
    },
    {
        "name": "control",
        "patch": os.path.join(HERE, "fixtures", "control.patch"),
        "target": os.path.join(HERE, "fixtures", "control_target.py"),
        "target_path": "tools/examples/normalize_name.py",
        "mode": "warn",
    },
]


def run_case(case: dict, workdir: str) -> dict:
    target = os.path.join(workdir, case["target_path"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(case["target"], target)
    out_json = os.path.join(workdir, f"{case['name']}-findings.json")
    out_md = os.path.join(workdir, f"{case['name']}-comment.md")
    proc = subprocess.run(
        [sys.executable, TOOLS,
         "--diff", case["patch"], "--repo-root", workdir,
         "--out-json", out_json, "--out-md", out_md],
        capture_output=True, text=True,
        # Must exceed the reviewer's own worst case (call_hub: 2 attempts x
        # TIMEOUT_S + retry sleep = ~603s), otherwise a slow-but-successful
        # run is killed and recorded as FAIL "timeout", conflating hub
        # latency with a reviewer defect (caught by the pr-agent review).
        timeout=900,
    )
    result: dict = {"name": case["name"], "rc": proc.returncode,
                    "stderr": proc.stderr.strip()[-400:]}
    if proc.returncode == 0:
        with open(out_json, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        result["findings"] = data["findings"]
        result["meta"] = data["meta"]
    return result


def judge(case: dict, result: dict) -> tuple[str, str]:
    if result["rc"] == 3:
        return "SKIP", "no ASTRA_API_KEY"
    if result["rc"] != 0:
        return "FAIL", f"reviewer exited {result['rc']}: {result['stderr']}"
    findings = result["findings"]
    if case["mode"] == "hard":
        citing = [f for f in findings
                  if f["file"].endswith(case["target_path"].rsplit("/", 1)[-1])
                  or case["target_path"] in f["file"]]
        strong = [f for f in citing if f["severity"] in ("high", "medium")]
        if not citing:
            return "FAIL", f"planted issue not seen at all ({len(findings)} findings elsewhere: " \
                           f"{[f['title'] for f in findings]})"
        if not strong:
            return "FAIL", f"planted issue seen but under-ranked: {[(f['severity'], f['title']) for f in citing]}"
        return "PASS", f"{len(strong)} finding(s) on the planted file: {[f['title'] for f in strong]}"
    # control: no high findings allowed; medium/low are a recorded warning
    highs = [f for f in findings if f["severity"] == "high"]
    if highs:
        return "FAIL", f"false high on clean diff: {[f['title'] for f in highs]}"
    if findings:
        return "PASS", f"clean diff, {len(findings)} low/medium (over-alert, recorded): " \
                       f"{[(f['severity'], f['title']) for f in findings]}"
    return "PASS", "clean diff, no findings"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canary-only", action="store_true",
                    help="run only the canary case (fast preflight)")
    args = ap.parse_args()

    if not os.environ.get("ASTRA_API_KEY", "").strip():
        print("[ai-review-eval] SKIP: ASTRA_API_KEY not set; the reviewer is unverified")
        return 0

    cases = [c for c in FIXTURES if not (args.canary_only and c["mode"] != "hard")]
    failures = 0
    skipped = 0
    with tempfile.TemporaryDirectory() as workdir:
        for case in cases:
            try:
                result = run_case(case, workdir)
            except subprocess.TimeoutExpired:
                result = {"name": case["name"], "rc": 4, "stderr": "timeout"}
            status, detail = judge(case, result)
            elapsed = result.get("meta", {}).get("elapsed_s", "?")
            print(f"[ai-review-eval] {status:4s} {case['name']:8s} ({elapsed}s) {detail}")
            if status == "FAIL":
                failures += 1
            elif status == "SKIP":
                skipped += 1
    if skipped == len(cases):
        return 0
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
