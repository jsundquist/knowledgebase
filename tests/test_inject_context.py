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
    query = inject_context.build_fts_query("How does the auth system behave?")
    assert '"auth"' in query
    assert '"system"' in query
    assert '"behave"' in query


def test_build_fts_query_drops_stopwords():
    query = inject_context.build_fts_query("what is the auth for this")
    assert query == '"auth"'


def test_build_fts_query_quotes_fts_operators():
    query = inject_context.build_fts_query("not auth and near jwt")
    assert query == '"auth" OR "jwt"'


def test_build_fts_query_only_stopwords():
    assert inject_context.build_fts_query("what about this") == ""


def test_build_fts_query_skips_short_words():
    query = inject_context.build_fts_query("is it ok to do this")
    # Words under 3 chars should be excluded; split to check whole tokens
    tokens = query.split(" OR ")
    assert '"is"' not in tokens
    assert '"it"' not in tokens
    assert '"ok"' not in tokens


def test_build_fts_query_empty_prompt():
    assert inject_context.build_fts_query("") == ""


def test_search_returns_relevant_entries(populated_db):
    results = inject_context.search(str(populated_db), "my-app", '"auth" OR "jwt"')
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


def _run(db, project, prompt, session_id=""):
    sys.argv = ["inject_context.py", str(db), project, prompt, session_id]
    try:
        inject_context.main()
    except SystemExit:
        pass


def test_block_includes_ids_and_is_capped(tmp_db, capsys):
    conn = get_conn()
    with conn:
        pid = get_or_create_project(conn, "big")
        for i in range(30):
            conn.execute(
                "INSERT INTO entries (project_id, type, title, body, tags, created, updated) VALUES (?,?,?,?,?,?,?)",
                (pid, "note", f"widget note {i}", "widget " + "x" * 5000, "", 1.0, 1.0),
            )
    conn.close()
    _run(tmp_db, "big", "tell me about widget", "s1")
    out = capsys.readouterr().out
    assert "(id " in out
    assert len(out.encode()) <= inject_context.MAX_BYTES


def test_superseded_and_stale_entries_not_injected(populated_db, capsys):
    conn = get_conn()
    with conn:
        conn.execute("UPDATE entries SET status='stale' WHERE title='Auth uses JWT'")
    conn.close()
    _run(populated_db, "my-app", "how does auth work", "s1")
    assert "Auth uses JWT" not in capsys.readouterr().out


def test_injects_once_per_session(populated_db, capsys):
    _run(populated_db, "my-app", "how does auth work", "s1")
    assert "<kb-context>" in capsys.readouterr().out
    _run(populated_db, "my-app", "how does auth work", "s1")
    assert capsys.readouterr().out == ""
    _run(populated_db, "my-app", "how does auth work", "s2")
    assert "<kb-context>" in capsys.readouterr().out


def test_updated_entry_is_reinjected(populated_db, capsys):
    _run(populated_db, "my-app", "how does auth work", "s1")
    capsys.readouterr()
    conn = get_conn()
    with conn:
        conn.execute("UPDATE entries SET body='changed', updated=updated+10 WHERE title='Auth uses JWT'")
    conn.close()
    _run(populated_db, "my-app", "how does auth work", "s1")
    out = capsys.readouterr().out
    assert "Auth uses JWT" in out
    assert "Use PostgreSQL" not in out


def test_first_prompt_gets_index_even_without_match(populated_db, capsys):
    _run(populated_db, "my-app", "zzznomatch qqqnomatch", "s1")
    assert "Use PostgreSQL" in capsys.readouterr().out


def test_no_session_id_only_injects_matches(populated_db, capsys):
    _run(populated_db, "my-app", "zzznomatch qqqnomatch")
    assert capsys.readouterr().out == ""


def test_automated_prompt_skipped(populated_db, capsys):
    _run(populated_db, "my-app", "[SYSTEM NOTIFICATION] agent finished auth work", "s1")
    assert capsys.readouterr().out == ""
    _run(populated_db, "my-app", "<task-notification>auth done</task-notification>", "s1")
    assert capsys.readouterr().out == ""


def test_single_oversized_entry_is_truncated_to_cap(tmp_db, capsys):
    conn = get_conn()
    with conn:
        pid = get_or_create_project(conn, "huge")
        conn.execute(
            "INSERT INTO entries (project_id, type, title, body, tags, created, updated) VALUES (?,?,?,?,?,?,?)",
            (pid, "note", "widget " + "T" * 5000, "widget body", "", 1.0, 1.0),
        )
    conn.close()
    _run(tmp_db, "huge", "tell me about widget", "s1")
    out = capsys.readouterr().out
    assert "widget" in out
    assert out.rstrip("\n").endswith("</kb-context>")
    assert len(out.encode()) <= inject_context.MAX_BYTES


def test_no_session_id_with_match_excludes_recent_index(populated_db, capsys):
    _run(populated_db, "my-app", "how does auth work")
    out = capsys.readouterr().out
    assert "Auth uses JWT" in out
    assert "Use PostgreSQL" not in out
