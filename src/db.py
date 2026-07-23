"""Database setup and helpers for the knowledgebase MCP server."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_PATH = Path.home() / ".claude" / "knowledgebase.db"

ENTRY_TYPES = {"idea", "finding", "understanding", "decision", "context", "question", "note"}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL UNIQUE,
                created  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                type        TEXT NOT NULL DEFAULT 'note',
                title       TEXT NOT NULL,
                body        TEXT NOT NULL DEFAULT '',
                tags        TEXT NOT NULL DEFAULT '',
                created     REAL NOT NULL,
                updated     REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS entries_project ON entries(project_id);
            CREATE INDEX IF NOT EXISTS entries_type    ON entries(type);

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                title,
                body,
                tags,
                content='entries',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                INSERT INTO entries_fts(rowid, title, body, tags)
                VALUES (new.id, new.title, new.body, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, title, body, tags)
                VALUES ('delete', old.id, old.title, old.body, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, title, body, tags)
                VALUES ('delete', old.id, old.title, old.body, old.tags);
                INSERT INTO entries_fts(rowid, title, body, tags)
                VALUES (new.id, new.title, new.body, new.tags);
            END;
        """)
    conn.close()


def get_or_create_project(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    now = time.time()
    cur = conn.execute("INSERT INTO projects (name, created) VALUES (?, ?)", (name, now))
    return cur.lastrowid


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
