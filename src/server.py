"""
knowledgebase MCP server — tracks key ideas, findings, and understanding per project.

Tools (6):                          Prompts (2):
  kb_add_entry    add a knowledge entry    project_context   load prior context
  kb_search       full-text search         capture_session   save session learnings
  kb_get_project  all entries for project
  kb_list_projects list all projects
  kb_update_entry  edit an entry
  kb_delete_entry  remove an entry
  kb_get_entry     fetch single entry
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

import prompts
import tools
from db import init_db

mcp = FastMCP("knowledgebase")

tools.register(mcp)
prompts.register(mcp)


if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    if not quiet:
        sys.stderr.write("knowledgebase MCP — launching server…\n")

    init_db()
    mcp.run(transport="stdio")
