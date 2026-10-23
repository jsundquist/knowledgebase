"""Append one line to the shared hook log (~/.claude/knowledgebase-hook.log).

Never raises: logging must not break a hook. Also usable from shell:
    python3 hook_log.py <source> <message>
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def log_path() -> Path:
    return Path.home() / ".claude" / "knowledgebase-hook.log"


def log(source: str, message: str) -> None:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(f"{datetime.now().isoformat()} {source}: {message}\n")
    except OSError:
        pass


if __name__ == "__main__":
    log(sys.argv[1] if len(sys.argv) > 1 else "hook", " ".join(sys.argv[2:]))
