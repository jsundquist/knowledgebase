"""Tests for database initialization and helpers."""

import sqlite3

import db as db_module
from db import get_conn, get_or_create_project, init_db


def test_init_creates_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"projects", "entries"}.issubset(tables)


def test_init_creates_fts_table(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "entries_fts" in tables


def test_init_is_idempotent(tmp_db, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    init_db()  # second call should not raise
    init_db()  # third for good measure


def test_get_or_create_project_creates(tmp_db):
    conn = get_conn()
    pid = get_or_create_project(conn, "my-project")
    assert isinstance(pid, int)
    assert pid > 0


def test_get_or_create_project_is_idempotent(tmp_db):
    conn = get_conn()
    pid1 = get_or_create_project(conn, "my-project")
    pid2 = get_or_create_project(conn, "my-project")
    assert pid1 == pid2


def test_get_or_create_project_distinct(tmp_db):
    conn = get_conn()
    pid1 = get_or_create_project(conn, "project-a")
    pid2 = get_or_create_project(conn, "project-b")
    assert pid1 != pid2
