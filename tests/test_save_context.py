"""Tests for the PreCompact/SessionEnd save_context hook."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from db import get_conn, init_db

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import save_context


def write_transcript(path, turns):
    """turns: list of (role, text) tuples -> JSONL transcript file."""
    lines = []
    for role, text in turns:
        lines.append(json.dumps({"message": {"role": role, "content": text}}))
    path.write_text("\n".join(lines) + "\n")


def test_flatten_transcript_extracts_user_and_assistant_text():
    raw = [
        json.dumps({"message": {"role": "user", "content": "fix the bug"}}) + "\n",
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "text", "text": "Found it, fixing now."},
            {"type": "tool_use", "name": "Edit", "input": {}},
        ]}}) + "\n",
        json.dumps({"message": {"role": "tool", "content": "tool output noise"}}) + "\n",
    ]
    text = save_context.flatten_transcript(raw)
    assert "User: fix the bug" in text
    assert "Assistant: Found it, fixing now." in text
    assert "tool output noise" not in text


def test_flatten_transcript_skips_malformed_lines():
    raw = ["not json\n", json.dumps({"message": {"role": "user", "content": "hi"}}) + "\n"]
    text = save_context.flatten_transcript(raw)
    assert "User: hi" in text


def test_truncate_text_keeps_tail():
    text = "a" * 100
    result = save_context.truncate_text(text, max_chars=10)
    assert result.endswith("a" * 10)
    assert "truncated" in result


def test_truncate_text_noop_when_short():
    text = "short"
    assert save_context.truncate_text(text, max_chars=100) == text


def test_read_new_lines_returns_delta(tmp_path):
    transcript = tmp_path / "t.jsonl"
    write_transcript(transcript, [("user", "one"), ("assistant", "two")])

    new_lines, total = save_context.read_new_lines(str(transcript), 0)
    assert total == 2
    assert len(new_lines) == 2

    new_lines, total = save_context.read_new_lines(str(transcript), 1)
    assert total == 2
    assert len(new_lines) == 1


def test_summarize_via_cmd_parses_json_output():
    entry = save_context.summarize_via_cmd(
        "some transcript text",
        cmd="python3 -c \"print('{\\\"title\\\": \\\"T\\\", \\\"body\\\": \\\"B\\\", \\\"tags\\\": \\\"x\\\", \\\"type\\\": \\\"note\\\"}')\"",
    )
    assert entry == {"title": "T", "body": "B", "tags": "x", "type": "note"}


def test_summarize_via_cmd_handles_bad_output():
    entry = save_context.summarize_via_cmd("text", cmd="echo not-json")
    assert entry is None


def test_summarize_via_cmd_handles_nonzero_exit():
    entry = save_context.summarize_via_cmd("text", cmd="exit 1")
    assert entry is None


def test_summarize_prefers_cmd_over_api_key(monkeypatch):
    monkeypatch.setenv("KB_SUMMARIZER_CMD", "echo '{\"title\": \"x\", \"body\": \"y\", \"tags\": \"\", \"type\": \"note\"}'")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    entry = save_context.summarize("text")
    assert entry["title"] == "x"


def test_summarize_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("KB_SUMMARIZER_CMD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert save_context.summarize("text") is None


def test_hook_state_roundtrip(tmp_db):
    conn = get_conn()
    assert save_context.get_last_line(conn, "/tmp/foo.jsonl") == 0
    save_context.set_last_line(conn, "/tmp/foo.jsonl", 5)
    conn.commit()
    assert save_context.get_last_line(conn, "/tmp/foo.jsonl") == 5
    save_context.set_last_line(conn, "/tmp/foo.jsonl", 9)
    conn.commit()
    assert save_context.get_last_line(conn, "/tmp/foo.jsonl") == 9
    conn.close()


def test_save_entry_tags_auto_saved_and_source(tmp_db):
    conn = get_conn()
    entry_id = save_context.save_entry(
        conn, "my-app", {"title": "T", "body": "B", "tags": "custom", "type": "finding"}, "clear"
    )
    conn.commit()
    row = conn.execute("SELECT type, title, body, tags FROM entries WHERE id = ?", (entry_id,)).fetchone()
    assert row[0] == "finding"
    assert row[1] == "T"
    assert "auto-saved" in row[3]
    assert "clear" in row[3]
    assert "custom" in row[3]
    conn.close()


def test_run_end_to_end_writes_entry_and_advances_state(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("KB_SUMMARIZER_CMD", "echo '{\"title\": \"Session summary\", \"body\": \"did stuff\", \"tags\": \"\", \"type\": \"context\"}'")

    transcript = tmp_path / "t.jsonl"
    write_transcript(transcript, [("user", "fix the bug"), ("assistant", "fixed it")])

    payload = {"transcript_path": str(transcript), "hook_event_name": "PreCompact", "cwd": "/repo/my-app"}
    save_context.run(payload, str(tmp_db))

    conn = get_conn()
    rows = conn.execute("SELECT title, tags FROM entries").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Session summary"
    assert "compact" in rows[0][1]
    assert save_context.get_last_line(conn, str(transcript)) == 2
    conn.close()


def test_run_is_noop_on_second_call_with_no_new_lines(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("KB_SUMMARIZER_CMD", "echo '{\"title\": \"S\", \"body\": \"b\", \"tags\": \"\", \"type\": \"context\"}'")

    transcript = tmp_path / "t.jsonl"
    write_transcript(transcript, [("user", "hello")])
    payload = {"transcript_path": str(transcript), "hook_event_name": "SessionEnd", "cwd": "/repo/my-app"}

    save_context.run(payload, str(tmp_db))
    save_context.run(payload, str(tmp_db))

    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert count == 1
    conn.close()


def test_run_noop_when_no_summarizer_configured(tmp_db, tmp_path, monkeypatch):
    monkeypatch.delenv("KB_SUMMARIZER_CMD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    transcript = tmp_path / "t.jsonl"
    write_transcript(transcript, [("user", "hello")])
    payload = {"transcript_path": str(transcript), "hook_event_name": "SessionEnd", "cwd": "/repo/my-app"}

    save_context.run(payload, str(tmp_db))

    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert count == 0
    conn.close()


def test_run_noop_when_transcript_missing(tmp_db):
    payload = {"transcript_path": "/nonexistent/path.jsonl", "hook_event_name": "SessionEnd", "cwd": "/repo/my-app"}
    save_context.run(payload, str(tmp_db))  # should not raise


def test_run_noop_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_SUMMARIZER_CMD", "echo '{\"title\": \"S\", \"body\": \"b\", \"tags\": \"\", \"type\": \"context\"}'")
    transcript = tmp_path / "t.jsonl"
    write_transcript(transcript, [("user", "hello")])
    payload = {"transcript_path": str(transcript), "hook_event_name": "SessionEnd", "cwd": "/repo/my-app"}
    save_context.run(payload, str(tmp_path / "no-such.db"))  # should not raise
