"""Knowledgebase MCP tools."""

from __future__ import annotations

import time
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from db import ENTRY_TYPES, get_conn, get_or_create_project

EntryType = Literal["idea", "finding", "understanding", "decision", "context", "question", "note"]


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def kb_add_entry(
        project: str,
        title: str,
        body: str,
        type: EntryType = "note",
        tags: str = "",
    ) -> dict:
        """Add a knowledge entry to a project.

        Use this to record key ideas, findings, decisions, and understandings
        as you work on a project. Call this proactively when you discover
        something important about a codebase, make a design decision, or
        identify a key constraint.

        Args:
            project: Project name (e.g. "transcript-search-mcp", "my-app").
            title:   Short descriptive title for this entry.
            body:    Full explanation, context, and details.
            type:    One of: idea, finding, understanding, decision, context, question, note.
            tags:    Comma-separated keywords (e.g. "auth,security,database").
        """
        if type not in ENTRY_TYPES:
            return {"error": f"Invalid type '{type}'. Must be one of: {', '.join(sorted(ENTRY_TYPES))}"}

        now = time.time()
        conn = get_conn()
        try:
            with conn:
                project_id = get_or_create_project(conn, project)
                cur = conn.execute(
                    "INSERT INTO entries (project_id, type, title, body, tags, created, updated) VALUES (?,?,?,?,?,?,?)",
                    (project_id, type, title, body, tags.strip(), now, now),
                )
                entry_id = cur.lastrowid
            return {"id": entry_id, "project": project, "type": type, "title": title, "status": "added"}
        finally:
            conn.close()

    @mcp.tool()
    def kb_search(
        query: str,
        project: Optional[str] = None,
        type: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search knowledge entries using full-text search.

        Searches titles, bodies, and tags. Use this to recall what's known
        about a project before starting work, or to find a specific decision
        or finding.

        Args:
            query:   Search terms (FTS5 syntax supported, e.g. "auth*", "database OR schema").
            project: Narrow to a specific project (optional).
            type:    Narrow to a specific entry type (optional).
            limit:   Max results (default 20).
        """
        conn = get_conn()
        try:
            params: list = [query]
            project_join = ""
            project_filter = ""
            type_filter = ""

            if project:
                project_join = "JOIN projects p ON e.project_id = p.id"
                project_filter = "AND p.name = ?"
                params.append(project)
            else:
                project_join = "JOIN projects p ON e.project_id = p.id"

            if type:
                type_filter = "AND e.type = ?"
                params.append(type)

            params.append(limit)

            rows = conn.execute(f"""
                SELECT e.id, p.name AS project, e.type, e.title, e.body, e.tags,
                       e.created, e.updated,
                       rank
                FROM entries_fts
                JOIN entries e ON entries_fts.rowid = e.id
                {project_join}
                WHERE entries_fts MATCH ?
                {project_filter}
                {type_filter}
                ORDER BY rank
                LIMIT ?
            """, params).fetchall()

            return [dict(r) for r in rows]
        finally:
            conn.close()

    @mcp.tool()
    def kb_get_project(project: str, type: Optional[str] = None) -> dict:
        """Get all knowledge entries for a project.

        Returns a summary of the project and all its entries, grouped by type.
        Use this at the start of work on a project to load prior context.

        Args:
            project: Project name.
            type:    Filter to a specific entry type (optional).
        """
        conn = get_conn()
        try:
            proj_row = conn.execute("SELECT id, created FROM projects WHERE name = ?", (project,)).fetchone()
            if not proj_row:
                return {"error": f"Project '{project}' not found"}

            type_filter = "AND e.type = ?" if type else ""
            params = [proj_row["id"]]
            if type:
                params.append(type)

            rows = conn.execute(f"""
                SELECT e.id, e.type, e.title, e.body, e.tags, e.created, e.updated
                FROM entries e
                WHERE e.project_id = ?
                {type_filter}
                ORDER BY e.type, e.created
            """, params).fetchall()

            by_type: dict[str, list] = {}
            for r in rows:
                d = dict(r)
                by_type.setdefault(d["type"], []).append(d)

            return {
                "project": project,
                "total_entries": len(rows),
                "by_type": by_type,
            }
        finally:
            conn.close()

    @mcp.tool()
    def kb_list_projects() -> list[dict]:
        """List all projects in the knowledgebase with entry counts.

        Use this to see what projects have accumulated knowledge.
        """
        conn = get_conn()
        try:
            rows = conn.execute("""
                SELECT p.name, p.created,
                       COUNT(e.id) AS entry_count,
                       MAX(e.updated) AS last_updated
                FROM projects p
                LEFT JOIN entries e ON e.project_id = p.id
                GROUP BY p.id
                ORDER BY last_updated DESC NULLS LAST
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @mcp.tool()
    def kb_update_entry(
        id: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        tags: Optional[str] = None,
        type: Optional[str] = None,
    ) -> dict:
        """Update an existing knowledge entry.

        Args:
            id:    Entry ID (from kb_add_entry or kb_search results).
            title: New title (optional).
            body:  New body (optional).
            tags:  New tags (optional).
            type:  New type (optional).
        """
        if type and type not in ENTRY_TYPES:
            return {"error": f"Invalid type '{type}'. Must be one of: {', '.join(sorted(ENTRY_TYPES))}"}

        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (id,)).fetchone()
            if not row:
                return {"error": f"Entry {id} not found"}

            new_title = title if title is not None else row["title"]
            new_body = body if body is not None else row["body"]
            new_tags = tags.strip() if tags is not None else row["tags"]
            new_type = type if type is not None else row["type"]

            with conn:
                conn.execute(
                    "UPDATE entries SET title=?, body=?, tags=?, type=?, updated=? WHERE id=?",
                    (new_title, new_body, new_tags, new_type, time.time(), id),
                )
            return {"id": id, "status": "updated"}
        finally:
            conn.close()

    @mcp.tool()
    def kb_delete_entry(id: int) -> dict:
        """Delete a knowledge entry by ID.

        Args:
            id: Entry ID to delete.
        """
        conn = get_conn()
        try:
            row = conn.execute("SELECT title FROM entries WHERE id = ?", (id,)).fetchone()
            if not row:
                return {"error": f"Entry {id} not found"}
            with conn:
                conn.execute("DELETE FROM entries WHERE id = ?", (id,))
            return {"id": id, "title": row["title"], "status": "deleted"}
        finally:
            conn.close()

    @mcp.tool()
    def kb_get_entry(id: int) -> dict:
        """Get a single knowledge entry by ID.

        Args:
            id: Entry ID.
        """
        conn = get_conn()
        try:
            row = conn.execute("""
                SELECT e.id, p.name AS project, e.type, e.title, e.body, e.tags,
                       e.created, e.updated
                FROM entries e
                JOIN projects p ON e.project_id = p.id
                WHERE e.id = ?
            """, (id,)).fetchone()
            if not row:
                return {"error": f"Entry {id} not found"}
            return dict(row)
        finally:
            conn.close()
