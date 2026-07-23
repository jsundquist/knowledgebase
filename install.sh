#!/usr/bin/env bash
# Installs the knowledgebase MCP server, UserPromptSubmit hook, and Stop hook
# into ~/.claude/settings.json (follows symlinks). Safe to re-run.
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"
# MCP server paths go into ~/.claude.json (Claude Code's primary config file)
# The UserPromptSubmit hook goes into settings.json (committed) since the hook
# script itself resolves its own absolute path at runtime via $BASH_SOURCE.
CLAUDE_JSON="$HOME/.claude.json"
SETTINGS_GLOBAL="$(python3 -c "import os; print(os.path.realpath(os.path.expanduser('~/.claude/settings.json')))")"

echo "==> knowledgebase: setting up Python venv..."
if ! command -v uv &>/dev/null; then
    echo "ERROR: 'uv' is not installed. Install it via Homebrew: brew install uv" >&2
    exit 1
fi
uv sync --quiet

echo "==> knowledgebase: patching $CLAUDE_JSON (MCP server)..."
python3 - "$CLAUDE_JSON" "$REPO_DIR" "$VENV" <<'PYEOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
repo_dir      = sys.argv[2]
venv          = sys.argv[3]

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}

settings.setdefault("mcpServers", {})["knowledgebase"] = {
    "type": "stdio",
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

hooks = settings.setdefault("hooks", {})

def register_hook(hooks, event, cmd):
    entries = hooks.setdefault(event, [])
    entries[:] = [h for h in entries if cmd not in str(h)]
    entries.append({"hooks": [{"type": "command", "command": cmd}]})

submit_cmd = f"{repo_dir}/hooks/user_prompt_submit.sh"
stop_cmd   = f"{repo_dir}/hooks/stop.sh"

register_hook(hooks, "UserPromptSubmit", submit_cmd)
register_hook(hooks, "Stop", stop_cmd)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
print(f"  UserPromptSubmit hook     → {submit_cmd}")
print(f"  Stop hook                 → {stop_cmd}")
PYEOF

echo "==> knowledgebase: install complete."
echo "    Restart Claude Code to pick up the new MCP server and hook."
