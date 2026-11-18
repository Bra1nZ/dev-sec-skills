#!/usr/bin/env python3
"""Diff-scoped LLM review for pull requests — the "own CodeRabbit" MVP.

Reads a git diff plus the new content of the changed files, asks the
project's model hub for security/correctness findings on the changed lines
only, and writes machine (JSON) and human (markdown) reports.

Honest limits, stated up front:
  * the diff is reviewed in per-file chunks (the reasoning-model hub cannot
    digest one large payload — measured), one model call per chunk; no
    agentic file exploration, no memory between runs, no incremental
    "seen before" state; cross-file interactions spanning chunks are not seen;
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
MAX_FILE_LINES = 300
MAX_FILE_CHARS = 4_000
MAX_FINDINGS = 20
# GLM-5.3 is a reasoning model: with a large single payload its invisible
# reasoning phase eats any token budget (measured: 4k and 16k budgets both
# hit finish_reason=length with empty content on the MVP's own ~70k-char
# diff; 32k timed out at 300s), and the hub accepts thinking={"type":
# "disabled"} but does not honor it. The fix that measurably works is shape,
# not size: the diff is split by file and reviewed in chunks.
MAX_TOKENS = 16000
TIMEOUT_S = 300
# Measured boundary on the hub, probed on the hardest real material: a
# ~10k-char payload answers in ~100s; 14k and larger hit finish_reason=length
# with empty content (the reasoning phase scales with input). The FULL
# payload — diff section PLUS file contents — must stay under PAYLOAD_BUDGET.
CHUNK_MAX_CHARS = 3_500
PAYLOAD_BUDGET = 9_500
MAX_CHUNKS = 16

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


def split_diff_by_file(diff_text: str) -> list[tuple[str, str]]:
    """Split a unified diff into (path, section) per changed file."""
    matches = list(DIFF_FILE_RE.finditer(diff_text))
    sections = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(diff_text)
        sections.append((match.group(2), diff_text[match.start():end]))
    return sections


def group_chunks(sections: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Greedy grouping: pack sections into chunks within the char budget.

    A single section larger than the budget gets a chunk of its own (it is
    truncated later by the normal diff-truncation path, loudly).
    """
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for section in sections:
        sec_len = len(section[1])
        if current and size + sec_len > CHUNK_MAX_CHARS:
            chunks.append(current)
            current, size = [], 0
        current.append(section)
        size += sec_len
    if current:
        chunks.append(current)
    return chunks


def build_payload(diff_text: str, repo_root: str) -> tuple[str, list[str], bool]:
    """System+user message content within the payload budget."""
    diff = diff_text
    truncated_diff = False
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n<diff truncated at %d chars>" % MAX_DIFF_CHARS
        truncated_diff = True

    # The hub's hard limit is on the FULL payload (see PAYLOAD_BUDGET), so
    # file contents get whatever the diff section leaves of the budget.
    budget = PAYLOAD_BUDGET - len(diff)
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
        "thinking": {"type": "disabled"},
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
                finish = data["choices"][0].get("finish_reason")
                raise HubError(
                    "empty model content"
                    + (f" (finish_reason={finish}; reasoning likely consumed the token budget)"
                       if finish == "length" else "")
                )
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
        f"{meta['files_reviewed']} file(s) in {meta['chunks']} chunk(s)"
        + (f", {meta['unreviewed_chunks']} chunk(s) over the chunk cap NOT reviewed"
           if meta.get("unreviewed_chunks") else "")
        + (f", {len(meta['chunk_errors'])} chunk(s) FAILED: review is PARTIAL"
           if meta.get("chunk_errors") else "")
        + (f", {len(meta['truncated_chunks'])} chunk(s) reviewed on truncated diffs"
           if meta.get("truncated_chunks") else "")
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
    sections = split_diff_by_file(diff_text)
    chunks = group_chunks(sections)
    unreviewed = 0
    if len(chunks) > MAX_CHUNKS:
        unreviewed = len(chunks) - MAX_CHUNKS
        chunks = chunks[:MAX_CHUNKS]

    findings: list[dict] = []
    chunk_errors: list[str] = []
    truncated_chunks: list[str] = []
    files_reviewed = 0
    for i, chunk in enumerate(chunks, start=1):
        chunk_diff = "\n".join(section for _, section in chunk)
        files_reviewed += len({p for p, _ in chunk if numbered_content(p, args.repo_root)})
        # Adaptive degradation: a chunk that hits finish_reason=length gets one
        # retry with half the diff section. The reasoning phase scales with
        # payload size AND material density, so the char budget alone cannot
        # predict it; halving + a loud "truncated" marking guarantees progress
        # without pretending the coverage was full.
        tried = 0
        while True:
            user_content, files, _trunc = build_payload(chunk_diff, args.repo_root)
            try:
                raw = call_hub(args.api_base, api_key, args.model, user_content)
                chunk_findings = parse_findings(raw)
                break
            except HubError as err:
                tried += 1
                if "finish_reason=length" not in str(err) or tried > 1 or len(chunk_diff) < 1_000:
                    chunk_errors.append(
                        f"chunk {i}/{len(chunks)} ({', '.join(p for p, _ in chunk)}): {err}")
                    print(f"ai-review: chunk {i}/{len(chunks)} failed: {err}", file=sys.stderr)
                    chunk_findings = None
                    break
                half = max(1_000, len(chunk_diff) // 2)
                # Keep the tail (truncation drops the head, but diff hunks for a
                # file start at its section head; halving keeps the first half
                # which is where the file's changed lines begin).
                chunk_diff = chunk_diff[:half] + f"\n<truncated for review: {len(chunk_diff) - half} chars dropped>"
                truncated_chunks.append(
                    f"chunk {i}/{len(chunks)} ({', '.join(p for p, _ in chunk)})")
                print(f"ai-review: chunk {i}/{len(chunks)}: retrying truncated "
                      f"({len(chunk_diff)} chars)", file=sys.stderr)
        if chunk_findings is None:
            continue
        findings.extend(chunk_findings)
        print(f"ai-review: chunk {i}/{len(chunks)}: {len(chunk_findings)} finding(s), "
              f"{len(files)} file(s)")
    if len(findings) > MAX_FINDINGS:
        findings = findings[:MAX_FINDINGS]
    findings.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["severity"], 3))
    elapsed = round(time.monotonic() - started, 1)

    meta = {
        "model": args.model,
        "elapsed_s": elapsed,
        "diff_chars": len(diff_text),
        "files_reviewed": files_reviewed,
        "chunks": len(chunks),
        "unreviewed_chunks": unreviewed,
        "chunk_errors": chunk_errors,
        "truncated_chunks": truncated_chunks,
        "truncated_diff": False,
    }
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "findings": findings}, fh, indent=2, ensure_ascii=False)
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(findings, meta))
    print(f"ai-review: {len(findings)} finding(s) in {elapsed}s "
          f"({len(chunks)} chunk(s), {len(chunk_errors)} failed)")
    if chunk_errors and not findings:
        raise HubError(f"all {len(chunk_errors)} chunk(s) failed; first: {chunk_errors[0]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HubError as err:
        print(f"ai-review: {err}", file=sys.stderr)
        sys.exit(4)
