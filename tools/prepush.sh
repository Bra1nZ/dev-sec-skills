#!/bin/bash
# Local pre-push gate — the repository's own CI analogue.
#
# Runs everything that would run after a push, BEFORE pushing: the repo
# quality gate (including the journal and transparency checks), the AI
# reviewer's canary preflight, and an AI diff review of the pending change.
# Nothing in this script talks to GitHub; the model key stays in the local
# file and is never printed.
#
# Designed to be runnable by a stranger with zero context: clone or worktree,
# one command, verdict-ready output.
#
# Usage:
#   tools/prepush.sh [--base REF] [--skip-canary] [--skip-ai-review]
#
# Exit codes: 0 all green, 1 any check failed.
set -euo pipefail

BASE="origin/main"
SKIP_CANARY=0
SKIP_AI=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --skip-canary) SKIP_CANARY=1; shift ;;
    --skip-ai-review) SKIP_AI=1; shift ;;
    *) echo "prepush: unknown argument $1" >&2; exit 2 ;;
  esac
done

TMPDIR_LOCAL="${TMPDIR:-/tmp/opencode}"
mkdir -p "$TMPDIR_LOCAL"
REPORT_MD="$TMPDIR_LOCAL/prepush-ai-review.md"
REPORT_JSON="$TMPDIR_LOCAL/prepush-ai-review.json"
DIFF_FILE="$TMPDIR_LOCAL/prepush-diff.diff"

# The model key is machine-local and never printed or committed. If absent,
# the AI stages self-skip with notices instead of failing the gate.
KEY_FILE="${CODEX_SECURITY_KEY_FILE:-$HOME/.config/codex-security/astra-api-key}"
if [ -z "${ASTRA_API_KEY:-}" ] && [ -f "$KEY_FILE" ]; then
  ASTRA_API_KEY="$(cat "$KEY_FILE")"
  export ASTRA_API_KEY
fi

echo "== prepush 1/3: repository gate (verify-ci, TRANSPARENCY_GATE=1) =="
make verify-ci TRANSPARENCY_GATE=1

if [ "$SKIP_CANARY" -eq 0 ]; then
  echo
  echo "== prepush 2/3: AI reviewer canary preflight =="
  # Without a key the eval self-skips with a notice (rc 0); with a key a
  # canary failure aborts the gate — an unverified reviewer must not speak.
  python3 evals/ai-review/run_evals.py --canary-only
fi

if [ "$SKIP_AI" -eq 0 ]; then
  echo
  echo "== prepush 3/3: AI diff review vs $BASE =="
  if git diff --quiet "$BASE...HEAD" 2>/dev/null && ! git diff --cached --quiet 2>/dev/null; then
    git diff --cached > "$DIFF_FILE"
  else
    git diff "$BASE...HEAD" > "$DIFF_FILE"
  fi
  if [ ! -s "$DIFF_FILE" ]; then
    echo "prepush: no diff vs $BASE — nothing to review"
  else
    python3 tools/ai_review.py \
      --diff "$DIFF_FILE" \
      --repo-root . \
      --out-json "$REPORT_JSON" \
      --out-md "$REPORT_MD"
    echo
    echo "---- AI review comment ($REPORT_MD) ----"
    cat "$REPORT_MD"
    echo "---- end AI review comment ----"
  fi
fi

echo
echo "== prepush: all stages done =="
