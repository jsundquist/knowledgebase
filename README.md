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
2. **MCP tools** let Claude read and write knowledge at any point during the session. This
   includes explicit human-in-the-loop capture: `kb_add_entry` isn't tied to auto-summarization —
   if you say "remember this" or "note that" mid-conversation, Claude calls it right then with
   your own framing, independent of (and more reliable than) anything the auto-save summarizer
   would infer later. See the `remember_this` MCP prompt below.
3. **`Stop` hook** (`hooks/stop.sh`) fires at the end of every session and reminds Claude to capture
   anything worth saving before it ends.
4. **`PreCompact`/`SessionEnd` hooks** (`hooks/pre_compact.sh`, `hooks/session_end.sh` →
   `hooks/save_context.py`) auto-save a summary of the conversation on `/compact` (manual or
   automatic) and `/clear`, so context isn't lost at those moments even if nothing was explicitly
   saved. See [Auto-save on /clear and /compact](#auto-save-on-clear-and-compact) below — this is
   opt-in and does nothing unless a summarizer backend is configured.

```
prompt submitted → relevant past knowledge injected → Claude works,
optionally saving new entries → session ends → Stop hook nudges a final capture pass
                                              (or /clear / /compact auto-saves a summary)
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

## MCP prompts

| Prompt | Purpose |
|---|---|
| `project_context` | Load all stored knowledge for a project at the start of a session |
| `capture_session` | Summarize and save findings/decisions at the end of a session |
| `remember_this` | Save something the user explicitly asked to remember, right now, in their own words |

## Architecture

```
src/
├── server.py    # FastMCP entrypoint (stdio transport)
├── tools.py     # MCP tool implementations
├── prompts.py   # project_context / capture_session / remember_this prompts
└── db.py        # SQLite schema (projects, entries, entries_fts) at ~/.claude/knowledgebase.db

hooks/
├── user_prompt_submit.sh  # UserPromptSubmit hook wrapper
├── inject_context.py      # builds and prints the <kb-context> block
├── stop.sh                # Stop hook — reminds Claude to save findings
├── pre_compact.sh         # PreCompact hook wrapper (manual + automatic /compact)
├── session_end.sh         # SessionEnd hook wrapper (fires save on /clear)
└── save_context.py        # summarizes the transcript delta and writes an auto-saved entry

install.sh       # installer
```

## Auto-save on /clear and /compact

`/clear` and `/compact` (manual or automatic) don't give Claude a chance to save anything itself
— by the time a hook fires, the context is already wiped or compressed. `hooks/save_context.py`
handles this outside the model loop: it reads the JSONL transcript at the point the hook fires,
summarizes only the portion not already saved (so repeated auto-compactions in a long session
don't produce duplicate/overlapping entries), and writes the result directly into
`knowledgebase.db`, tagged `auto-saved` plus `clear` or `compact`.

This is **opt-in** — without a summarizer backend configured, both hooks no-op silently and
nothing is saved. Configure one of:

- **`KB_SUMMARIZER_CMD`** — a shell command that reads transcript text on stdin and writes a JSON
  object `{"title", "body", "tags", "type"}` to stdout (or `{"skip": true}` if there's nothing
  worth saving). Use this to plug in any summarization backend — a local model, a different
  provider, a script that calls out to whatever chat client you're using. This keeps the hook
  itself independent of any specific chat client or LLM vendor.
- **`ANTHROPIC_API_KEY`** — if set and `KB_SUMMARIZER_CMD` isn't, `save_context.py` calls the
  Anthropic Messages API directly (not the `claude` CLI) with a small model
  (`KB_SUMMARIZER_MODEL`, default `claude-haiku-4-5-20251001`) to produce the same JSON shape.
  **Note:** this sends the transcript delta to Anthropic's API on every `/clear`/`/compact` —
  a privacy and cost tradeoff worth deciding deliberately per machine, not just a config default.

Both hooks run the summarization step fully detached (`setsid`, backgrounded) so `/clear` and
`/compact` return immediately regardless of how long summarization takes.

## Install

Prerequisites: Python ≥3.11 and [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

```
./install.sh
```

This runs `uv sync`, registers the MCP server in `~/.claude.json`, wires all four hooks into
`~/.claude/settings.json`, and is safe to re-run. Restart Claude Code afterward to pick up the
changes.

## Development

```
uv run pytest
```

Runs the test suite (`tests/test_db.py`, `tests/test_tools.py`, `tests/test_inject_context.py`,
`tests/test_save_context.py`).
