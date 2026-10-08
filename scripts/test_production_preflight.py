from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from production_preflight import inspect_and_backup


def test_inspect_and_backup_preserves_tables(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    data_dir.mkdir()
    database = data_dir / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO audit_log DEFAULT VALUES")

    result = inspect_and_backup(data_dir, backup_dir)

    assert result["integrity"] == "ok"
    assert result["table_counts"] == {"audit_log": 1}
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1


def test_inspect_and_backup_refuses_missing_database(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="refusing to create"):
        inspect_and_backup(data_dir, tmp_path / "backups")


def test_inspect_and_backup_requires_absolute_paths() -> None:
    with pytest.raises(ValueError, match="absolute"):
        inspect_and_backup(Path("relative-data"), Path("relative-backups"))
