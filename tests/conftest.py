"""Shared fixtures for knowledgebase tests."""

import sys
from pathlib import Path

import pytest

# Allow imports from src/ without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import db as db_module


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite database for each test."""
    db_path = tmp_path / "test_kb.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path
