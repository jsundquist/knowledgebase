#!/usr/bin/env bash
# SessionEnd hook — when the session ended because of /clear, summarizes the
# transcript delta since the last save and writes it to the knowledgebase in the
# background. Skips for other SessionEnd reasons (exit, logout, etc).
#
# NOTE: the exact payload field/value identifying a /clear-triggered end hasn't been
# verified against a real payload yet — this checks a few plausible field names
# ("matcher", "reason", "trigger") for a "clear" value. Confirm and tighten this once
# a real SessionEnd payload has been captured (see plan's Verification section).
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
print(d.get('matcher') or d.get('reason') or d.get('trigger') or '')
" 2>/dev/null || true)"

if [[ "$(echo "$REASON" | tr '[:upper:]' '[:lower:]')" != "clear" ]]; then
    exit 0
fi

TMP="$(mktemp)"
printf '%s' "$PAYLOAD" > "$TMP"

setsid bash -c "\"$VENV/bin/python\" \"$SAVE\" < \"$TMP\"; rm -f \"$TMP\"" </dev/null >/dev/null 2>&1 &
disown

exit 0
