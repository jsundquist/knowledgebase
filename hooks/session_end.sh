#!/usr/bin/env bash
# SessionEnd hook — when the session ended because of /clear, summarizes the
# transcript delta since the last save and writes it to the knowledgebase in the
# background. Skips for other SessionEnd reasons (resume, logout,
# prompt_input_exit, bypass_permissions_disabled, other).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/.venv"
SAVE="$REPO_DIR/hooks/save_context.py"

PAYLOAD="$(cat)"

REASON="$(printf '%s' "$PAYLOAD" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get('reason') or '')
" 2>/dev/null || true)"

if [[ "$(echo "$REASON" | tr '[:upper:]' '[:lower:]')" != "clear" ]]; then
    exit 0
fi

TMP="$(mktemp)"
printf '%s' "$PAYLOAD" > "$TMP"

setsid bash -c "\"$VENV/bin/python\" \"$SAVE\" < \"$TMP\"; rm -f \"$TMP\"" </dev/null >/dev/null 2>&1 &
disown

exit 0
