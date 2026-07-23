#!/usr/bin/env bash
# Stop hook — after a session with real work, prompt Claude to save any
# findings not yet captured in the knowledgebase.
# Exits silently if the session doesn't meet the threshold (no edits made).
set -euo pipefail

# Claude Code passes a JSON payload on stdin with session metadata
PAYLOAD="$(cat)"

# Only trigger if files were actually edited this session
EDIT_COUNT="$(echo "$PAYLOAD" | python3 -c "
import sys, json
d = json.load(sys.stdin)
stats = d.get('session', {}).get('stats', {})
print(stats.get('filesEdited', 0))
" 2>/dev/null || echo 0)"

[[ "$EDIT_COUNT" -gt 0 ]] || exit 0

PROJECT="$(basename "$PWD")"

cat <<EOF
<kb-reminder>
Files were edited in this session. Before finishing, check whether any of the
following are worth saving to the knowledgebase for project "$PROJECT":
- Non-obvious decisions made or constraints discovered
- Bug root causes or subtle behavioral findings
- Patterns or conventions observed in this codebase
- Open questions that remain unresolved

Call kb_add_entry(...) for anything not yet captured. Skip this if entries were
already saved during the session.
</kb-reminder>
EOF
