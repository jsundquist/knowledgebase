"""MCP prompts for the knowledgebase server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.prompt()
    def project_context(project: str) -> str:
        """Load prior knowledge about a project before starting work.

        Use this at the beginning of a session when working on a known project.
        It will retrieve all stored entries so you can resume with full context.
        """
        return (
            f"Use kb_get_project(project='{project}') to load all stored knowledge about "
            f"this project. Summarize the key findings, decisions, and open questions "
            f"before proceeding with work."
        )

    @mcp.prompt()
    def capture_session(project: str) -> str:
        """Capture key learnings from this session into the knowledgebase.

        Use this at the end of a session to save important findings and decisions.
        """
        return (
            f"Review this conversation and identify: (1) key findings about the '{project}' "
            f"codebase, (2) decisions made and their rationale, (3) open questions or TODOs, "
            f"(4) important constraints or gotchas discovered. "
            f"For each, call kb_add_entry(project='{project}', ...) with an appropriate type. "
            f"Be concise but complete — these entries will be loaded in future sessions."
        )
