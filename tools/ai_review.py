#!/usr/bin/env python3
"""Diff-scoped LLM review for pull requests — the "own CodeRabbit" MVP.

Reads a git diff plus the new content of the changed files, asks the
project's model hub for security/correctness findings on the changed lines
only, and writes machine (JSON) and human (markdown) reports.

Honest limits, stated up front:
  * one model call per run — no agentic file exploration, no memory between
    runs, no incremental "seen before" state;
  * findings are review input, not evidence: nothing here is journaled or
    anchored yet;
  * a "0 findings" result is meaningless on its own. The canary eval
    (evals/ai-review/run_evals.py) is the minimum trust precondition —
    if the reviewer misses a planted issue, its silence proves nothing.

Usage:
  python3 tools/ai_review.py --diff /tmp/pr.diff --repo-root . \
      --out-json /tmp/findings.json --out-md /tmp/comment.md

Exit codes: 0 ok, 3 no API key (skip), 4 hub error, 5 unparseable reply.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API_BASE = "https://hub.ai.astra-team.ru/api/v1/inference/v1"
DEFAULT_MODEL = "GLM-5.3"
MARKER = "<!-- dev-sec-skills-ai-review -->"

MAX_FILES = 30
MAX_DIFF_CHARS = 70_000
MAX_FILE_LINES = 500
MAX_FILE_CHARS = 14_000
MAX_TOTAL_CHARS = 110_000
MAX_FINDINGS = 20
MAX_TOKENS = 4000
TIMEOUT_S = 180

SYSTEM_PROMPT = """You are a security-focused code reviewer for a git diff (a changeset).
Rules:
1. Review ONLY the added/changed lines (lines starting with '+') and their direct consequences.
2. The full content of the changed files is provided for context; use it.
3. Report only concrete, defensible issues: security vulnerabilities, correctness bugs, broken invariants, leaked secrets, unsafe handling of untrusted input.
4. No style opinions, no hypotheticals without line-level evidence.
5. Cite the exact path and the line number in the NEW version of the file.
6. Respond with ONLY a JSON array (no prose, no code fences). Element shape:
   {"severity": "high"|"medium"|"low", "file": "path", "line": <int>, "title": "short", "detail": "why, and how to fix"}
   Return [] if there is nothing defensible. Do not invent findings to seem useful."""

DIFF_FILE_RE = re.compile(r'^diff --git a/(.+?) b/(.+?)$', re.MULTILINE)


class HubError(Exception):
    pass


def changed_files(diff_text: str) -> list[str]:
    """Files touched by the diff, in first-appearance order."""
    seen: list[str] = []
    for match in DIFF_FILE_RE.finditer(diff_text):
        path = match.group(2)
        if path not in seen:
            seen.append(path)
    return seen


def numbered_content(path: str, repo_root: str) -> str | None:
    """New-version file content with line numbers, capped; None if unreadable."""
    full = os.path.join(repo_root, path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    lines = lines[:MAX_FILE_LINES]
    out = []
    used = 0
    for i, line in enumerate(lines, start=1):
        entry = f"{i:5d}: {line.rstrip()}"
        used += len(entry) + 1
        if used > MAX_FILE_CHARS:
            out.append(f"{i:5d}: <truncated: file exceeds {MAX_FILE_CHARS} chars>")
            break
        out.append(entry)
    if len(lines) == MAX_FILE_LINES:
        out.append("<truncated: max line count reached>")
    return "\n".join(out)


def build_payload(diff_text: str, repo_root: str) -> tuple[str, list[str], bool]:
    """System+user message content within the char budget."""
    diff = diff_text
    truncated_diff = False
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n<diff truncated at %d chars>" % MAX_DIFF_CHARS
        truncated_diff = True

    budget = MAX_TOTAL_CHARS - len(diff)
    files = changed_files(diff_text)[:MAX_FILES]
    blocks = []
    for path in files:
        if budget <= 0:
            break
        content = numbered_content(path, repo_root)
        if content is None:
            continue
        header = f"### {path}"
        body = content
        if len(header) + len(body) + 2 > budget:
            body = body[: budget - len(header) - 40] + "\n<truncated for budget>"
        budget -= len(header) + len(body) + 2
        blocks.append(f"{header}\n{body}")

    skipped = max(0, len(changed_files(diff_text)) - len(files))
    user = (
        f"Changed files: {len(files)}" + (f" (+{skipped} more not shown)" if skipped else "")
        + f"; diff size: {len(diff)} chars" + (" (truncated)" if truncated_diff else "")
        + ".\n\n--- DIFF ---\n" + diff
    )
    if blocks:
        user += "\n\n--- CHANGED FILE CONTENTS (new version, with line numbers) ---\n" + "\n\n".join(blocks)
    return user, files, truncated_diff


def call_hub(api_base: str, api_key: str, model: str, user_content: str) -> str:
    url = api_base.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": MAX_TOKENS,
    }).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(2):
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"].get("content")
            if not isinstance(content, str) or not content.strip():
                raise HubError("empty model content")
            return content
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                KeyError, IndexError, json.JSONDecodeError) as err:
            last_err = err
            if attempt == 0:
                time.sleep(3)
    raise HubError(f"hub call failed after retry: {last_err!r}")


def parse_findings(raw: str) -> list[dict]:
    """Extract a JSON array from the reply; tolerate code fences and prose."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise HubError("no JSON array in reply")
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, list):
        raise HubError("reply is not a JSON array")
    valid = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        severity = item.get("severity")
        if severity not in ("high", "medium", "low"):
            continue
        if not isinstance(item.get("file"), str) or not isinstance(item.get("title"), str):
            continue
        valid.append({
            "severity": severity,
            "file": item["file"],
            "line": int(item.get("line") or 0),
            "title": item["title"],
            "detail": str(item.get("detail") or ""),
        })
        if len(valid) >= MAX_FINDINGS:
            break
    return valid


def render_markdown(findings: list[dict], meta: dict) -> str:
    order = {"high": 0, "medium": 1, "low": 2}
    lines = [MARKER, "", "## AI diff review (MVP)", ""]
    if not findings:
        lines.append("No findings. One model call over the PR diff; "
                     "silence is not evidence (the canary eval must pass for this to mean anything).")
    else:
        lines.append(f"**{len(findings)} finding(s)** in changed lines:\n")
        lines.append("| Severity | File:line | Title | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for f in sorted(findings, key=lambda x: order.get(x["severity"], 3)):
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            lines.append(f"| {f['severity']} | `{loc}` | {f['title']} | {f['detail']} |")
    lines += [
        "",
        "---",
        f"<sub>model `{meta['model']}`, {meta['elapsed_s']}s, diff {meta['diff_chars']} chars, "
        f"{meta['files_reviewed']} file(s) in context"
        + (", diff truncated" if meta["truncated_diff"] else "")
        + ". One-shot diff review: input for triage, not evidence; not journaled.</sub>",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diff", required=True, help="path to the git diff file")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--api-base", default=DEFAULT_API_BASE)
    args = ap.parse_args()

    api_key = os.environ.get("ASTRA_API_KEY", "").strip()
    if not api_key:
        print("ai-review: ASTRA_API_KEY not set — skipping review", file=sys.stderr)
        return 3

    with open(args.diff, "r", encoding="utf-8", errors="replace") as fh:
        diff_text = fh.read()

    started = time.monotonic()
    user_content, files, truncated_diff = build_payload(diff_text, args.repo_root)
    raw = call_hub(args.api_base, api_key, args.model, user_content)
    findings = parse_findings(raw)
    elapsed = round(time.monotonic() - started, 1)

    meta = {
        "model": args.model,
        "elapsed_s": elapsed,
        "diff_chars": len(diff_text),
        "files_reviewed": len(files),
        "truncated_diff": truncated_diff,
    }
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "findings": findings}, fh, indent=2, ensure_ascii=False)
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(findings, meta))
    print(f"ai-review: {len(findings)} finding(s) in {elapsed}s")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HubError as err:
        print(f"ai-review: {err}", file=sys.stderr)
        sys.exit(4)
