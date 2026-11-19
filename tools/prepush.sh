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
#   tools/prepush.sh [--base REF] [--skip-canary] [--skip-ai-review] [--skip-pragent]
#
# Exit codes: 0 all green, 1 any check failed.
set -euo pipefail

BASE="origin/main"
SKIP_CANARY=0
SKIP_AI=0
SKIP_PRAGENT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --skip-canary) SKIP_CANARY=1; shift ;;
    --skip-ai-review) SKIP_AI=1; shift ;;
    --skip-pragent) SKIP_PRAGENT=1; shift ;;
    *) echo "prepush: unknown argument $1" >&2; exit 2 ;;
  esac
done

TMPDIR_LOCAL="${TMPDIR:-/tmp/opencode}"
mkdir -p "$TMPDIR_LOCAL"
REPORT_MD="$TMPDIR_LOCAL/prepush-ai-review.md"
REPORT_JSON="$TMPDIR_LOCAL/prepush-ai-review.json"
PRAGENT_MD="$TMPDIR_LOCAL/prepush-pragent-review.md"
DIFF_FILE="$TMPDIR_LOCAL/prepush-diff.diff"

# The model key is machine-local and never printed or committed. If absent,
# the AI stages self-skip with notices instead of failing the gate.
KEY_FILE="${CODEX_SECURITY_KEY_FILE:-$HOME/.config/codex-security/astra-api-key}"
if [ -z "${ASTRA_API_KEY:-}" ] && [ -f "$KEY_FILE" ]; then
  ASTRA_API_KEY="$(cat "$KEY_FILE")"
  export ASTRA_API_KEY
fi

# Second engine (measured 2026-11-19, see spec/ai-review/README.md): pr-agent
# with its built-in chunked review over the same hub. The two engines' finding
# sets overlap near zero, so both run when available. pr-agent exits 0 even on
# total failure, so the output is verified by content, not by exit code.
PRAGENT_BIN="$HOME/.local/opt/pr-agent-venv/bin/pr-agent"

run_pragent_review() {
  if [ ! -x "$PRAGENT_BIN" ]; then
    echo "prepush: pr-agent venv not found ($PRAGENT_BIN) — skipping second engine"
    return 0
  fi
  if [ -z "${ASTRA_API_KEY:-}" ]; then
    echo "prepush: no API key — skipping pr-agent review"
    return 0
  fi
  echo
  echo "== prepush 3b: second engine (pr-agent chunked review) =="
  export OPENAI__KEY="$ASTRA_API_KEY"
  export OPENAI__API_BASE="${AI_REVIEW_API_BASE:-https://hub.ai.astra-team.ru/api/v1/inference/v1}"
  export CONFIG__MODEL="${AI_REVIEW_MODEL:-openai/GLM-5.3}"
  export CONFIG__CUSTOM_MODEL_MAX_TOKENS=8000
  export CONFIG__AI_TIMEOUT=300
  export CONFIG__FALLBACK_MODELS=""
  export PR_REVIEWER__ENABLE_LARGE_PR_CHUNKING=true
  export PR_REVIEWER__MAX_NUMBER_OF_CALLS=5
  if timeout 1800 "$PRAGENT_BIN" --diff-file "$DIFF_FILE" review > "$PRAGENT_MD" 2>&1; then
    if grep -q 'PR Reviewer Guide' "$PRAGENT_MD"; then
      echo "prepush: pr-agent review OK ($PRAGENT_MD)"
      echo "---- pr-agent review ($PRAGENT_MD) ----"
      grep -v 'INFO \|WARNING \|DEBUG ' "$PRAGENT_MD" | sed -n '/PR Reviewer Guide/,$p'
      echo "---- end pr-agent review ----"
    else
      echo "prepush: WARNING — pr-agent exited 0 but produced no review (engine failure); see $PRAGENT_MD"
    fi
  else
    echo "prepush: WARNING — pr-agent failed (rc=$?); output in $PRAGENT_MD"
  fi
}

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
    if [ "$SKIP_PRAGENT" -eq 0 ]; then
      run_pragent_review
    fi
  fi
fi

echo
echo "== prepush: all stages done =="
