# knowledgebase

An MCP server for Claude Code that gives Claude persistent, per-project memory — ideas, findings,
decisions, and open questions — so sessions build on prior context instead of starting cold.

## Why

Claude Code sessions are stateless: architecture decisions, gotchas, and open questions discovered
in one session are gone by the next, and have to be re-discovered from scratch. This project stores
that knowledge in a local SQLite database and wires it into Claude Code's hook system so it's
surfaced and captured automatically, with no manual note-taking required.

## How it works

1. **`UserPromptSubmit` hook** (`hooks/user_prompt_submit.sh` → `hooks/inject_context.py`) runs on
   every prompt. It full-text-searches the current project's saved entries (falling back to the
   most recently updated ones if there's no match) and injects a `<kb-context>` block into the
   conversation.
2. **MCP tools** let Claude read and write knowledge at any point during the session.
3. **`Stop` hook** (`hooks/stop.sh`) fires at the end of every session and reminds Claude to capture
   anything worth saving before it ends.

```
prompt submitted → relevant past knowledge injected → Claude works,
optionally saving new entries → session ends → Stop hook nudges a final capture pass
```

## MCP tools

| Tool | Purpose |
|---|---|
| `kb_add_entry` | Save a new entry (`project`, `title`, `body`, `type`, `tags`) |
| `kb_search` | Full-text search across entries, optionally scoped by project/type |
| `kb_get_project` | Fetch all entries for a project, grouped by type |
| `kb_list_projects` | List known projects with entry counts and last-updated |
| `kb_update_entry` | Partially update an existing entry |
| `kb_delete_entry` | Delete an entry by id |
| `kb_get_entry` | Fetch a single entry by id |

Entry `type` is one of: `idea`, `finding`, `understanding`, `decision`, `context`, `question`, `note`.

## Architecture

```
src/
├── server.py    # FastMCP entrypoint (stdio transport)
├── tools.py     # MCP tool implementations
├── prompts.py   # project_context / capture_session prompts
└── db.py        # SQLite schema (projects, entries, entries_fts) at ~/.claude/knowledgebase.db

hooks/
├── user_prompt_submit.sh  # UserPromptSubmit hook wrapper
├── inject_context.py      # builds and prints the <kb-context> block
└── stop.sh                 # Stop hook — reminds Claude to save findings

install.sh       # installer
```

## Install

Prerequisites: Python ≥3.11 and [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

```
./install.sh
```

This runs `uv sync`, registers the MCP server in `~/.claude.json`, wires both hooks into
`~/.claude/settings.json`, and is safe to re-run. Restart Claude Code afterward to pick up the
changes.

## Development

```
uv run pytest
```

Runs the test suite (`tests/test_db.py`, `tests/test_tools.py`, `tests/test_inject_context.py`).
