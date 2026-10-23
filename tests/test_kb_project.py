"""Tests for project-name resolution."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
from kb_project import resolve_project


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_non_git_dir_uses_basename(tmp_path):
    d = tmp_path / "plain-dir"
    d.mkdir()
    assert resolve_project(str(d)) == "plain-dir"


def test_repo_and_subdir_resolve_to_repo_name(tmp_path):
    repo = tmp_path / "my-repo"
    (repo / "sub").mkdir(parents=True)
    _git(repo, "init", "-q")
    assert resolve_project(str(repo)) == "my-repo"
    assert resolve_project(str(repo / "sub")) == "my-repo"


def test_worktree_resolves_to_parent_repo(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
    wt = repo / ".claude" / "worktrees" / "agent-abc"
    _git(repo, "worktree", "add", "-q", str(wt))
    assert resolve_project(str(wt)) == "my-repo"
