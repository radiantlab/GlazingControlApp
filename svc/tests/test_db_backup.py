from __future__ import annotations

import sqlite3
from datetime import datetime

from app import db_backup


def test_backup_database_once_creates_consistent_sqlite_copy(tmp_path):
    db_file = tmp_path / "audit.db"
    backup_dir = tmp_path / "backups"

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE sensor_readings (sensor_id TEXT, value REAL)")
        conn.execute(
            "INSERT INTO sensor_readings (sensor_id, value) VALUES (?, ?)",
            ("EKO-00", 123.4),
        )

    backup_path = db_backup.backup_database_once(
        db_file=str(db_file),
        backup_dir=str(backup_dir),
        timestamp=datetime(2026, 6, 30, 12, 0, 0),
    )

    assert backup_path == backup_dir / "audit-20260630-120000.db"
    assert backup_path.exists()

    with sqlite3.connect(backup_path) as conn:
        row = conn.execute("SELECT sensor_id, value FROM sensor_readings").fetchone()

    assert row == ("EKO-00", 123.4)


def test_start_database_backup_worker_from_env_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SVC_DB_BACKUP_INTERVAL_HOURS", raising=False)
    monkeypatch.delenv("SVC_DB_BACKUP_DIR", raising=False)

    assert db_backup.start_database_backup_worker_from_env() is None


def test_start_database_backup_worker_from_env_rejects_invalid_interval(monkeypatch):
    monkeypatch.setenv("SVC_DB_BACKUP_INTERVAL_HOURS", "daily")
    monkeypatch.setenv("SVC_DB_BACKUP_DIR", "C:/Box/GlazingBackups")

    assert db_backup.start_database_backup_worker_from_env() is None
