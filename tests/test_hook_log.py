"""Every hook failure leaves a line in ~/.claude/knowledgebase-hook.log."""

import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))
from kb_project import resolve_project


def _run(cmd, home, stdin=""):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)


def _log(home):
    p = home / ".claude" / "knowledgebase-hook.log"
    return p.read_text() if p.exists() else ""


def test_save_context_logs_malformed_payload(tmp_path):
    r = _run([sys.executable, str(HOOKS / "save_context.py")], tmp_path, stdin="not json{")
    assert r.returncode == 0
    assert "save_context" in _log(tmp_path)
    assert "malformed" in _log(tmp_path)


def test_prompt_submit_logs_json_parse_failure(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "knowledgebase.db").write_text("")
    r = _run(["bash", str(HOOKS / "user_prompt_submit.sh")], tmp_path, stdin="not json{")
    assert r.returncode == 0
    assert "user_prompt_submit" in _log(tmp_path)


def test_session_end_logs_json_parse_failure(tmp_path):
    r = _run(["bash", str(HOOKS / "session_end.sh")], tmp_path, stdin="not json{")
    assert r.returncode == 0
    assert "session_end" in _log(tmp_path)


def test_git_fallback_is_logged(tmp_path, monkeypatch):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git = fake_bin / "git"
    git.write_text("#!/bin/sh\necho 'unknown option: --path-format' >&2\nexit 129\n")
    git.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    d = tmp_path / "plain"
    d.mkdir()
    assert resolve_project(str(d)) == "plain"
    assert "git" in _log(home)
    assert "fallback" in _log(home)


def test_non_git_dir_is_not_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    d = tmp_path / "plain"
    d.mkdir()
    resolve_project(str(d))
    assert _log(tmp_path / "home") == ""
