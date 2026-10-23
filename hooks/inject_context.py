"""
Queries knowledgebase.db for entries relevant to the current project and prompt,
then prints a compact <kb-context> block to stdout for Claude to consume.

The block is capped (MAX_BYTES), shows titles plus a short body excerpt with entry
ids, and only includes active entries. Entries already injected in this session
(and unchanged since) are skipped, so a project injects once per session and then
only what newly matches.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
import traceback
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from db import migrate  # noqa: E402

LOG_PATH = Path.home() / ".claude" / "knowledgebase-hook.log"
MAX_BYTES = 2000
EXCERPT_CHARS = 240
MATCH_LIMIT = 5
INDEX_LIMIT = 5
STATE_TTL_SECONDS = 14 * 24 * 3600

STOPWORDS = frozenset("""
    the and for are but not you all can had her was one our out has have this that with
    from they will would there their what about which when make like time just him know
    take into year your some could them see other than then now look only come its over
    think also back after use two how our work first well way even new want because any
    these give day most are does did should why where who while here let need please
    should still too very via yes yet near
""".split())


@contextmanager
def open_db(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open the knowledgebase, apply migrations, and always close on exit."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        migrate(conn)
        yield conn
    finally:
        conn.close()


def is_automated(prompt: str) -> bool:
    head = prompt.lstrip()[:200]
    return head.startswith("[SYSTEM NOTIFICATION") or "<task-notification" in head


def build_fts_query(prompt: str) -> str:
    """OR together up to 10 distinct, quoted, non-stopword terms.

    Quoting keeps FTS5 operators (AND/OR/NOT/NEAR) in the prompt from being parsed.
    Returns "" when no meaningful terms remain.
    """
    seen: list[str] = []
    for word in re.findall(r"[a-zA-Z0-9_]{3,}", prompt.lower()):
        if word not in STOPWORDS and word not in seen:
            seen.append(word)
    terms = seen[:10]
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in terms)


def search(db_path: str, project: str, query: str, limit: int = MATCH_LIMIT) -> list[dict]:
    with open_db(db_path) as conn:
        rows = conn.execute("""
            SELECT e.id, e.type, e.title, e.body, e.tags, e.updated
            FROM entries_fts
            JOIN entries e ON entries_fts.rowid = e.id
            JOIN projects p ON e.project_id = p.id
            WHERE entries_fts MATCH ?
              AND p.name = ?
              AND e.status = 'active'
            ORDER BY bm25(entries_fts, 10.0, 1.0, 5.0)
            LIMIT ?
        """, (query, project, limit)).fetchall()
        return [dict(r) for r in rows]


def get_project_entries(db_path: str, project: str, limit: int = INDEX_LIMIT) -> list[dict]:
    with open_db(db_path) as conn:
        rows = conn.execute("""
            SELECT e.id, e.type, e.title, e.body, e.tags, e.updated
            FROM entries e
            JOIN projects p ON e.project_id = p.id
            WHERE p.name = ? AND e.status = 'active'
            ORDER BY e.updated DESC
            LIMIT ?
        """, (project, limit)).fetchall()
        return [dict(r) for r in rows]


# --- Session state (inject_state table) ------------------------------------

def load_seen_entries(conn: sqlite3.Connection, session_id: str) -> dict[int, float]:
    """Map entry id -> `updated` stamp for entries already injected this session."""
    rows = conn.execute(
        "SELECT entry_id, updated FROM inject_state WHERE session_id = ?", (session_id,)
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def record_injected(conn: sqlite3.Connection, session_id: str, entries: list[dict]) -> None:
    """Remember injected entries for the session and prune expired state rows."""
    now = time.time()
    with conn:
        conn.execute("DELETE FROM inject_state WHERE ts < ?", (now - STATE_TTL_SECONDS,))
        conn.executemany(
            "INSERT OR REPLACE INTO inject_state (session_id, entry_id, updated, ts) VALUES (?,?,?,?)",
            [(session_id, e["id"], e["updated"], now) for e in entries],
        )


# --- Rendering ---------------------------------------------------------------

def _excerpt(body: str) -> str:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()][:2]
    text = " ".join(lines)
    if len(text) > EXCERPT_CHARS:
        text = text[: EXCERPT_CHARS - 1].rstrip() + "…"
    return text


def format_entry(e: dict) -> str:
    day = datetime.fromtimestamp(e["updated"]).strftime("%Y-%m-%d")
    out = [f"[{e['type'].upper()}] {e['title']} (id {e['id']}, updated {day})"]
    excerpt = _excerpt(e["body"] or "")
    if excerpt:
        out.append(excerpt)
    return "\n".join(out)


def render_block(project: str, entries: list[dict]) -> tuple[str, list[dict]]:
    """Build the block, adding entries until MAX_BYTES. Returns (text, entries used)."""
    header = f"<kb-context>\nProject: {project}\n\n"
    footer = "Excerpts only — call kb_get_entry(id) for the full text.\n</kb-context>"
    text = header
    used: list[dict] = []
    for e in entries:
        chunk = format_entry(e) + "\n\n"
        if used and len((text + chunk + footer).encode()) > MAX_BYTES:
            break
        text += chunk
        used.append(e)
    return text + footer, used


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(0)

    db_path, project, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
    session_id = sys.argv[4] if len(sys.argv) > 4 else ""

    if is_automated(prompt):
        sys.exit(0)

    fts_query = build_fts_query(prompt)
    matches = search(db_path, project, fts_query) if fts_query else []

    with open_db(db_path) as conn:
        seen: dict[int, float] = {}
        first_in_session = False
        if session_id:
            seen = load_seen_entries(conn, session_id)
            first_in_session = not seen

        candidates = list(matches)
        if first_in_session:
            have = {e["id"] for e in candidates}
            candidates += [e for e in get_project_entries(db_path, project) if e["id"] not in have]

        fresh = [e for e in candidates if seen.get(e["id"]) != e["updated"]]
        if not fresh:
            sys.exit(0)

        text, used = render_block(project, fresh)

        if session_id:
            record_injected(conn, session_id, used)

    print(text)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a") as f:
                f.write(f"{datetime.now().isoformat()} inject_context failed\n{traceback.format_exc()}\n")
        except OSError:
            pass
        sys.exit(0)
