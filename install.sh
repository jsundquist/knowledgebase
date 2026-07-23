#!/usr/bin/env bash
# Installs the knowledgebase MCP server and UserPromptSubmit hook into
# ~/.claude/settings.json (follows symlinks). Safe to re-run.
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"
# MCP server paths go into settings.local.json (machine-specific, not committed)
# The UserPromptSubmit hook goes into settings.json (committed) since the hook
# script itself resolves its own absolute path at runtime via $BASH_SOURCE.
SETTINGS_LOCAL="$HOME/.claude/settings.local.json"
SETTINGS_GLOBAL="$(python3 -c "import os; print(os.path.realpath(os.path.expanduser('~/.claude/settings.json')))")"

echo "==> knowledgebase: setting up Python venv..."
if ! command -v uv &>/dev/null; then
    echo "ERROR: 'uv' is not installed. Install it via Homebrew: brew install uv" >&2
    exit 1
fi
uv sync --quiet

echo "==> knowledgebase: patching $SETTINGS_LOCAL (MCP server)..."
python3 - "$SETTINGS_LOCAL" "$REPO_DIR" "$VENV" <<'PYEOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
repo_dir      = sys.argv[2]
venv          = sys.argv[3]

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

settings.setdefault("mcpServers", {})["knowledgebase"] = {
    "command": f"{venv}/bin/python",
    "args": [f"{repo_dir}/src/server.py", "--quiet"],
    "env": {"PYTHONPATH": f"{repo_dir}/src"},
}

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"  knowledgebase MCP server  → {venv}/bin/python")
PYEOF

echo "==> knowledgebase: patching $SETTINGS_GLOBAL (hook)..."
python3 - "$SETTINGS_GLOBAL" "$REPO_DIR" <<'PYEOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
repo_dir      = sys.argv[2]

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

hook_cmd = f"{repo_dir}/hooks/user_prompt_submit.sh"
hooks = settings.setdefault("hooks", {})
submit_hooks = hooks.setdefault("UserPromptSubmit", [])

# Remove any stale knowledgebase hook entry, then re-add
submit_hooks[:] = [h for h in submit_hooks if hook_cmd not in str(h)]
submit_hooks.append({
    "hooks": [{"type": "command", "command": hook_cmd}]
})

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"  UserPromptSubmit hook     → {hook_cmd}")
PYEOF

echo "==> knowledgebase: install complete."
echo "    Restart Claude Code to pick up the new MCP server and hook."
