"""Tests for knowledgebase MCP tools."""

import db as db_module
import pytest
from db import get_conn, get_or_create_project
from tools import register
from mcp.server.fastmcp import FastMCP


@pytest.fixture()
def mcp_tools(tmp_db, monkeypatch):
    """Register tools against the isolated DB and return callable wrappers."""
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)

    mcp = FastMCP("test-kb")
    register(mcp)

    # Extract the underlying functions from the registered tools
    tool_map = {t.name: t.fn for t in mcp._tool_manager.list_tools()}
    return tool_map


# ---------------------------------------------------------------------------
# kb_add_entry
# ---------------------------------------------------------------------------

def test_add_entry_basic(mcp_tools):
    result = mcp_tools["kb_add_entry"](
        project="my-project", title="Auth uses JWT", body="JWTs are signed with RS256.", type="finding"
    )
    assert result["status"] == "added"
    assert "id" in result
    assert result["type"] == "finding"


def test_add_entry_defaults(mcp_tools):
    result = mcp_tools["kb_add_entry"](project="p", title="Quick note", body="body")
    assert result["type"] == "note"


def test_add_entry_invalid_type(mcp_tools):
    result = mcp_tools["kb_add_entry"](project="p", title="t", body="b", type="bogus")
    assert "error" in result


def test_add_entry_all_types(mcp_tools):
    for entry_type in ("idea", "finding", "understanding", "decision", "context", "question", "note"):
        result = mcp_tools["kb_add_entry"](project="p", title=f"title-{entry_type}", body="b", type=entry_type)
        assert result["status"] == "added", f"failed for type={entry_type}"


# ---------------------------------------------------------------------------
# kb_get_entry
# ---------------------------------------------------------------------------

def test_get_entry_roundtrip(mcp_tools):
    add = mcp_tools["kb_add_entry"](project="proj", title="My Title", body="My Body", tags="a,b")
    entry = mcp_tools["kb_get_entry"](id=add["id"])
    assert entry["title"] == "My Title"
    assert entry["body"] == "My Body"
    assert entry["tags"] == "a,b"
    assert entry["project"] == "proj"


def test_get_entry_not_found(mcp_tools):
    result = mcp_tools["kb_get_entry"](id=99999)
    assert "error" in result


# ---------------------------------------------------------------------------
# kb_update_entry
# ---------------------------------------------------------------------------

def test_update_entry_title(mcp_tools):
    add = mcp_tools["kb_add_entry"](project="p", title="Old Title", body="body")
    mcp_tools["kb_update_entry"](id=add["id"], title="New Title")
    entry = mcp_tools["kb_get_entry"](id=add["id"])
    assert entry["title"] == "New Title"
    assert entry["body"] == "body"  # unchanged


def test_update_entry_type(mcp_tools):
    add = mcp_tools["kb_add_entry"](project="p", title="t", body="b", type="note")
    mcp_tools["kb_update_entry"](id=add["id"], type="decision")
    entry = mcp_tools["kb_get_entry"](id=add["id"])
    assert entry["type"] == "decision"


def test_update_entry_invalid_type(mcp_tools):
    add = mcp_tools["kb_add_entry"](project="p", title="t", body="b")
    result = mcp_tools["kb_update_entry"](id=add["id"], type="invalid")
    assert "error" in result


def test_update_entry_not_found(mcp_tools):
    result = mcp_tools["kb_update_entry"](id=99999, title="x")
    assert "error" in result


# ---------------------------------------------------------------------------
# kb_delete_entry
# ---------------------------------------------------------------------------

def test_delete_entry(mcp_tools):
    add = mcp_tools["kb_add_entry"](project="p", title="to delete", body="b")
    result = mcp_tools["kb_delete_entry"](id=add["id"])
    assert result["status"] == "deleted"
    assert mcp_tools["kb_get_entry"](id=add["id"])["error"]


def test_delete_entry_not_found(mcp_tools):
    result = mcp_tools["kb_delete_entry"](id=99999)
    assert "error" in result


# ---------------------------------------------------------------------------
# kb_list_projects
# ---------------------------------------------------------------------------

def test_list_projects_empty(mcp_tools):
    assert mcp_tools["kb_list_projects"]() == []


def test_list_projects_after_add(mcp_tools):
    mcp_tools["kb_add_entry"](project="alpha", title="t", body="b")
    mcp_tools["kb_add_entry"](project="beta", title="t", body="b")
    projects = {p["name"] for p in mcp_tools["kb_list_projects"]()}
    assert projects == {"alpha", "beta"}


def test_list_projects_entry_count(mcp_tools):
    mcp_tools["kb_add_entry"](project="alpha", title="t1", body="b")
    mcp_tools["kb_add_entry"](project="alpha", title="t2", body="b")
    mcp_tools["kb_add_entry"](project="beta", title="t1", body="b")
    counts = {p["name"]: p["entry_count"] for p in mcp_tools["kb_list_projects"]()}
    assert counts["alpha"] == 2
    assert counts["beta"] == 1


# ---------------------------------------------------------------------------
# kb_get_project
# ---------------------------------------------------------------------------

def test_get_project_not_found(mcp_tools):
    result = mcp_tools["kb_get_project"](project="nonexistent")
    assert "error" in result


def test_get_project_groups_by_type(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="f1", body="b", type="finding")
    mcp_tools["kb_add_entry"](project="p", title="f2", body="b", type="finding")
    mcp_tools["kb_add_entry"](project="p", title="d1", body="b", type="decision")
    result = mcp_tools["kb_get_project"](project="p")
    assert result["total_entries"] == 3
    assert len(result["by_type"]["finding"]) == 2
    assert len(result["by_type"]["decision"]) == 1


def test_get_project_type_filter(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="f1", body="b", type="finding")
    mcp_tools["kb_add_entry"](project="p", title="n1", body="b", type="note")
    result = mcp_tools["kb_get_project"](project="p", type="finding")
    assert "finding" in result["by_type"]
    assert "note" not in result["by_type"]


# ---------------------------------------------------------------------------
# kb_search
# ---------------------------------------------------------------------------

def test_search_finds_by_title(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="database schema design", body="uses postgres")
    results = mcp_tools["kb_search"](query="database")
    assert any("database" in r["title"] for r in results)


def test_search_finds_by_body(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="auth notes", body="JWT tokens are short-lived")
    results = mcp_tools["kb_search"](query="JWT")
    assert len(results) > 0


def test_search_finds_by_tags(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="some title", body="some body", tags="security,oauth")
    results = mcp_tools["kb_search"](query="oauth")
    assert len(results) > 0


def test_search_project_scoped(mcp_tools):
    mcp_tools["kb_add_entry"](project="alpha", title="auth implementation", body="b")
    mcp_tools["kb_add_entry"](project="beta", title="auth configuration", body="b")
    results = mcp_tools["kb_search"](query="auth", project="alpha")
    assert all(r["project"] == "alpha" for r in results)


def test_search_no_results(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="something", body="body text")
    results = mcp_tools["kb_search"](query="zzznomatch")
    assert results == []


def test_search_type_filter(mcp_tools):
    mcp_tools["kb_add_entry"](project="p", title="auth finding", body="b", type="finding")
    mcp_tools["kb_add_entry"](project="p", title="auth decision", body="b", type="decision")
    results = mcp_tools["kb_search"](query="auth", type="finding")
    assert all(r["type"] == "finding" for r in results)
