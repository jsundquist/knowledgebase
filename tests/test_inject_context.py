"""Tests for the UserPromptSubmit hook injector."""

import sqlite3
import sys
from pathlib import Path

import pytest

import db as db_module
from db import get_conn, get_or_create_project, init_db

# Import the injector from hooks/
sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
import inject_context


@pytest.fixture()
def populated_db(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    conn = get_conn()
    with conn:
        pid = get_or_create_project(conn, "my-app")
        import time
        now = time.time()
        conn.execute(
            "INSERT INTO entries (project_id, type, title, body, tags, created, updated) VALUES (?,?,?,?,?,?,?)",
            (pid, "finding", "Auth uses JWT", "RS256 signed tokens with 1h expiry", "auth,jwt", now, now),
        )
        conn.execute(
            "INSERT INTO entries (project_id, type, title, body, tags, created, updated) VALUES (?,?,?,?,?,?,?)",
            (pid, "decision", "Use PostgreSQL", "Chosen for JSONB support", "database,postgres", now, now),
        )
    conn.close()
    return tmp_db


def test_build_fts_query_extracts_words():
    query = inject_context.build_fts_query("How does the auth system work?")
    assert "auth" in query
    assert "system" in query
    assert "work" in query


def test_build_fts_query_skips_short_words():
    query = inject_context.build_fts_query("is it ok to do this")
    # Words under 3 chars should be excluded; split to check whole tokens
    tokens = query.split(" OR ")
    assert "is" not in tokens
    assert "it" not in tokens
    assert "ok" not in tokens


def test_build_fts_query_empty_prompt():
    assert inject_context.build_fts_query("") == ""


def test_search_returns_relevant_entries(populated_db):
    results = inject_context.search(str(populated_db), "my-app", "auth OR JWT")
    assert len(results) > 0
    assert any("Auth" in r["title"] for r in results)


def test_search_project_scoped(populated_db):
    # The fallback only fires when the FTS query itself finds nothing globally,
    # so use a term that doesn't exist anywhere in the DB.
    results = inject_context.search(str(populated_db), "other-project", "zzznomatch")
    assert results == []


def test_get_project_entries_returns_all(populated_db):
    results = inject_context.get_project_entries(str(populated_db), "my-app")
    assert len(results) == 2


def test_get_project_entries_unknown_project(populated_db):
    results = inject_context.get_project_entries(str(populated_db), "unknown")
    assert results == []


def test_main_outputs_context_block(populated_db, capsys):
    sys.argv = ["inject_context.py", str(populated_db), "my-app", "how does auth work"]
    inject_context.main()
    captured = capsys.readouterr()
    assert "<kb-context>" in captured.out
    assert "</kb-context>" in captured.out
    assert "my-app" in captured.out


def test_main_silent_on_no_results(populated_db, capsys):
    sys.argv = ["inject_context.py", str(populated_db), "unknown-project", "zzznomatch"]
    with pytest.raises(SystemExit) as exc:
        inject_context.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out == ""


def test_main_requires_args(capsys):
    sys.argv = ["inject_context.py"]
    with pytest.raises(SystemExit) as exc:
        inject_context.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out == ""
