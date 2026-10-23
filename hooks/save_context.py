"""
PreCompact / SessionEnd hook — summarizes the transcript delta since the last save and writes
it to knowledgebase.db as an `auto-saved` entry. Fails silently (exit 0, no output) whenever
there's nothing to do or nothing is configured, so it never blocks `/clear` or `/compact`.

Summarization backend is pluggable:
  1. $KB_SUMMARIZER_CMD, if set — a subprocess that reads transcript text on stdin and writes
     a single JSON object {"title", "body", "tags", "type"} to stdout.
  2. $ANTHROPIC_API_KEY, if set — a direct HTTPS call to the Anthropic Messages API.
  3. Otherwise: skip. No summarizer configured, nothing is saved.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

from hook_log import log
from kb_project import resolve_project

MAX_CHARS = 20_000
SUBPROCESS_TIMEOUT_SECS = 60
HTTP_TIMEOUT_SECS = 60
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SUMMARY_INSTRUCTIONS = (
    "You are summarizing a slice of a coding-assistant conversation for a long-term "
    "knowledgebase entry. Read the transcript delta below and respond with ONLY a JSON object "
    '(no markdown fences, no commentary) of the shape {"title": str, "body": str, "tags": str, '
    '"type": str}. "type" must be one of: idea, finding, understanding, decision, context, '
    "question, note. \"tags\" is a comma-separated string. Keep \"body\" focused on what a "
    "future session would need to know: decisions made, findings, open questions, gotchas. If "
    "there is nothing worth remembering, respond with {\"skip\": true} instead."
)


def read_new_lines(transcript_path: str, last_line: int) -> tuple[list[str], int]:
    """Return (new raw JSONL lines, total line count) since `last_line`."""
    with open(transcript_path, encoding="utf-8") as f:
        all_lines = f.readlines()
    return all_lines[last_line:], len(all_lines)


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def flatten_transcript(raw_lines: list[str]) -> str:
    """Turn raw JSONL transcript lines into a plain-text User:/Assistant: turn log,
    skipping tool-call/tool-result noise and anything that fails to parse."""
    turns = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        role = None
        content = None
        if isinstance(obj, dict) and isinstance(obj.get("message"), dict):
            role = obj["message"].get("role")
            content = obj["message"].get("content")
        elif isinstance(obj, dict) and obj.get("role"):
            role = obj.get("role")
            content = obj.get("content")

        if role not in ("user", "assistant"):
            continue

        text = _extract_text(content).strip()
        if not text:
            continue

        turns.append(f"{role.capitalize()}: {text}")

    return "\n\n".join(turns)


def truncate_text(text: str, max_chars: int = MAX_CHARS) -> str:
    """Keep the most recent `max_chars` characters (the tail), noting truncation."""
    if len(text) <= max_chars:
        return text
    return "[... earlier portion truncated ...]\n\n" + text[-max_chars:]


def _parse_json_object(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def summarize_via_cmd(text: str, cmd: str) -> dict | None:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            input=text,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return _parse_json_object(result.stdout)


def summarize_via_anthropic(text: str, api_key: str) -> dict | None:
    model = os.environ.get("KB_SUMMARIZER_MODEL", DEFAULT_MODEL)
    payload = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": f"{SUMMARY_INSTRUCTIONS}\n\n---\n\n{text}"}
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    blocks = body.get("content", [])
    text_out = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    return _parse_json_object(text_out)


def summarize(text: str) -> dict | None:
    cmd = os.environ.get("KB_SUMMARIZER_CMD")
    if cmd:
        return summarize_via_cmd(text, cmd)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return summarize_via_anthropic(text, api_key)

    return None


def get_last_line(conn: sqlite3.Connection, transcript_path: str) -> int:
    row = conn.execute(
        "SELECT last_line FROM hook_state WHERE transcript_path = ?", (transcript_path,)
    ).fetchone()
    return row[0] if row else 0


def set_last_line(conn: sqlite3.Connection, transcript_path: str, last_line: int) -> None:
    conn.execute(
        "INSERT INTO hook_state (transcript_path, last_line) VALUES (?, ?) "
        "ON CONFLICT(transcript_path) DO UPDATE SET last_line = excluded.last_line",
        (transcript_path, last_line),
    )


def save_entry(conn: sqlite3.Connection, project: str, entry: dict, source_tag: str) -> int:
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (project,)).fetchone()
    if row:
        project_id = row[0]
    else:
        now = time.time()
        cur = conn.execute("INSERT INTO projects (name, created) VALUES (?, ?)", (project, now))
        project_id = cur.lastrowid

    entry_type = entry.get("type") or "context"
    tags = entry.get("tags") or ""
    tags = ",".join(t for t in [tags, "auto-saved", source_tag] if t)

    now = time.time()
    cur = conn.execute(
        "INSERT INTO entries (project_id, type, title, body, tags, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, entry_type, entry.get("title", "Session summary"), entry.get("body", ""), tags, now, now),
    )
    return cur.lastrowid


def run(payload: dict, db_path: str) -> None:
    transcript_path = payload.get("transcript_path")
    hook_event_name = payload.get("hook_event_name", "")
    source_tag = "clear" if hook_event_name == "SessionEnd" else "compact"

    if not transcript_path or not os.path.isfile(transcript_path):
        return
    if not os.path.isfile(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        last_line = get_last_line(conn, transcript_path)
        try:
            new_lines, total_lines = read_new_lines(transcript_path, last_line)
        except OSError:
            return

        if not new_lines:
            return

        text = flatten_transcript(new_lines)
        if not text.strip():
            set_last_line(conn, transcript_path, total_lines)
            conn.commit()
            return

        text = truncate_text(text)
        entry = summarize(text)

        if not entry or entry.get("skip"):
            return

        project = resolve_project(payload.get("cwd") or os.getcwd())
        save_entry(conn, project, entry, source_tag)
        set_last_line(conn, transcript_path, total_lines)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        log("save_context", f"malformed hook payload: {e}")
        sys.exit(0)

    db_path = os.environ.get("KB_DB_PATH") or os.path.expanduser("~/.claude/knowledgebase.db")

    try:
        run(payload, db_path)
    except Exception:
        # Fail open — this hook must never block /clear or /compact.
        log("save_context", f"failed: {traceback.format_exc()}")
        sys.exit(0)


if __name__ == "__main__":
    main()
