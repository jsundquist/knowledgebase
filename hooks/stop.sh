#!/usr/bin/env bash
# Stop hook — after any session, prompt Claude to save findings to the
# knowledgebase. Fires unconditionally; the reminder itself says to skip
# if nothing worth capturing came up.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$(python3 "$REPO_DIR/hooks/hook_log.py" --path)"
PROJECT="$("$REPO_DIR/.venv/bin/python" "$REPO_DIR/hooks/kb_project.py" "$PWD" 2>>"$LOG")" || {
    python3 "$REPO_DIR/hooks/hook_log.py" stop "project resolution failed; using directory name" || true
    PROJECT="$(basename "$PWD")"
}

cat <<EOF
<kb-reminder>
Before finishing, consider whether any of the following are worth saving to
the knowledgebase for project "$PROJECT":
- Architecture insights, key components, or non-obvious design decisions
- Constraints or gotchas discovered while reading or exploring the codebase
- Bug root causes or subtle behavioral findings
- Patterns or conventions observed in this codebase
- Open questions that remain unresolved

Call kb_add_entry(...) for anything useful for future sessions. Skip only if
nothing meaningful came up.
</kb-reminder>
EOF
