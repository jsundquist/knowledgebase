#!/usr/bin/env bash
# UserPromptSubmit hook — injects relevant knowledgebase context before Claude
# processes the prompt. Reads from ~/.claude/knowledgebase.db directly (no MCP
# round-trip needed). Exits silently on any error so it never blocks Claude.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$HOME/.claude/knowledgebase.db"
VENV="$REPO_DIR/.venv"
INJECT="$REPO_DIR/hooks/inject_context.py"

# Nothing to do if DB doesn't exist yet
[[ -f "$DB" ]] || exit 0

# Read the prompt from stdin (Claude Code passes it as JSON on stdin)
PAYLOAD="$(cat)"
LOG="$HOME/.claude/knowledgebase-hook.log"
PROMPT="$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null || true)"
SESSION_ID="$(echo "$PAYLOAD" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null || true)"

[[ -z "$PROMPT" ]] && exit 0

# Project key comes from the git common dir so worktrees map to their parent repo
PROJECT="$("$VENV/bin/python" "$REPO_DIR/hooks/kb_project.py" "$PWD" 2>>"$LOG" || basename "$PWD")"

# Run the injector — its stdout becomes the injected context block; failures are logged
"$VENV/bin/python" "$INJECT" "$DB" "$PROJECT" "$PROMPT" "$SESSION_ID" 2>>"$LOG" || true
