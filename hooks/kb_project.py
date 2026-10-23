"""
Resolves the knowledgebase project name for a working directory.

Uses the git common dir so a linked worktree (e.g. .claude/worktrees/agent-<id>)
maps to the same project as the repo it was created from. Falls back to the
directory name outside a git repo.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_log import log  # noqa: E402


def resolve_project(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        common = result.stdout.strip()
        if result.returncode == 0 and common:
            common = common.rstrip("/")
            if os.path.basename(common) == ".git":
                return os.path.basename(os.path.dirname(common))
            return os.path.basename(common).removesuffix(".git")
        if "not a git repository" not in result.stderr:
            log(
                "kb_project",
                f"git project resolution failed (rc={result.returncode}, {result.stderr.strip()!r}); "
                f"using directory-name fallback for {cwd}",
            )
    except (OSError, subprocess.SubprocessError) as e:
        log("kb_project", f"git unavailable ({e}); using directory-name fallback for {cwd}")
    return os.path.basename(cwd.rstrip("/")) or cwd


if __name__ == "__main__":
    print(resolve_project(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()))
