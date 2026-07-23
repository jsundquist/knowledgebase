"""
Queries knowledgebase.db for entries relevant to the current project and prompt,
then prints a <kb-context> block to stdout for Claude to consume.
"""
from __future__ import annotations

import sqlite3
import sys


def search(db_path: str, project: str, query: str, limit: int = 8) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Project-scoped FTS search
        rows = conn.execute("""
            SELECT e.type, e.title, e.body, e.tags
            FROM entries_fts
            JOIN entries e ON entries_fts.rowid = e.id
            JOIN projects p ON e.project_id = p.id
            WHERE entries_fts MATCH ?
              AND p.name = ?
            ORDER BY rank
            LIMIT ?
        """, (query, project, limit)).fetchall()

        # If no project-scoped hits, try global (preferences, style rules, etc.)
        if not rows:
            rows = conn.execute("""
                SELECT e.type, e.title, e.body, e.tags
                FROM entries_fts
                JOIN entries e ON entries_fts.rowid = e.id
                ORDER BY rank
                LIMIT ?
            """, (limit,)).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_project_entries(db_path: str, project: str, limit: int = 10) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT e.type, e.title, e.body, e.tags
            FROM entries e
            JOIN projects p ON e.project_id = p.id
            WHERE p.name = ?
            ORDER BY e.updated DESC
            LIMIT ?
        """, (project, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_fts_query(prompt: str) -> str:
    # Strip punctuation, take first 10 meaningful words as FTS terms
    import re
    words = re.findall(r"[a-zA-Z0-9_]{3,}", prompt)[:10]
    return " OR ".join(words) if words else ""


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(0)

    db_path, project, prompt = sys.argv[1], sys.argv[2], sys.argv[3]

    fts_query = build_fts_query(prompt)
    entries: list[dict] = []

    if fts_query:
        entries = search(db_path, project, fts_query)

    # Always include recent project entries if we have a project match
    if not entries:
        entries = get_project_entries(db_path, project)

    if not entries:
        sys.exit(0)

    lines = ["<kb-context>"]
    lines.append(f"Project: {project}")
    lines.append("")
    for e in entries:
        lines.append(f"[{e['type'].upper()}] {e['title']}")
        if e["body"]:
            lines.append(e["body"])
        if e["tags"]:
            lines.append(f"tags: {e['tags']}")
        lines.append("")
    lines.append("</kb-context>")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
