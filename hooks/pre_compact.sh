#!/usr/bin/env bash
# PreCompact hook — summarizes the transcript delta since the last save (manual or
# automatic compaction) and writes it to the knowledgebase in the background, so
# /compact returns immediately. No-ops silently if no summarizer backend is configured.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/.venv"
SAVE="$REPO_DIR/hooks/save_context.py"

PAYLOAD="$(cat)"
TMP="$(mktemp)"
printf '%s' "$PAYLOAD" > "$TMP"

setsid bash -c "\"$VENV/bin/python\" \"$SAVE\" < \"$TMP\"; rm -f \"$TMP\"" </dev/null >/dev/null 2>&1 &
disown

exit 0
