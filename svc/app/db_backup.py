from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import AUDIT_DB_FILE


logger = logging.getLogger(__name__)


def _parse_interval_hours(raw_value: str | None) -> float:
    if raw_value is None or raw_value.strip() == "":
        return 0.0
    try:
        return float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid SVC_DB_BACKUP_INTERVAL_HOURS=%r; database backups are disabled",
            raw_value,
        )
        return 0.0


def backup_database_once(
    *,
    db_file: str = AUDIT_DB_FILE,
    backup_dir: str,
    timestamp: datetime | None = None,
) -> Path:
    """Write a consistent SQLite backup copy and return the completed file path."""
    source_path = Path(db_file)
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {source_path}")

    stamp = (timestamp or datetime.now()).strftime("%Y%m%d-%H%M%S")
    destination = destination_dir / f"audit-{stamp}.db"
    temp_destination = destination.with_suffix(".db.tmp")

    source_conn = sqlite3.connect(str(source_path))
    backup_conn = sqlite3.connect(str(temp_destination))
    try:
        source_conn.backup(backup_conn)
    finally:
        backup_conn.close()
        source_conn.close()

    os.replace(temp_destination, destination)
    return destination


class DatabaseBackupWorker:
    def __init__(self, *, interval_hours: float, backup_dir: str, db_file: str = AUDIT_DB_FILE) -> None:
        self.interval_seconds = interval_hours * 60 * 60
        self.backup_dir = backup_dir
        self.db_file = db_file
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="db-backup", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                backup_path = backup_database_once(db_file=self.db_file, backup_dir=self.backup_dir)
                logger.info("SQLite database backup written to %s", backup_path)
            except Exception:
                logger.exception("SQLite database backup failed")

            if self._stop.wait(self.interval_seconds):
                return


def start_database_backup_worker_from_env() -> DatabaseBackupWorker | None:
    interval_hours = _parse_interval_hours(os.getenv("SVC_DB_BACKUP_INTERVAL_HOURS"))
    backup_dir = os.getenv("SVC_DB_BACKUP_DIR", "").strip()

    if interval_hours <= 0:
        logger.info("SQLite database backups disabled; set SVC_DB_BACKUP_INTERVAL_HOURS > 0 to enable")
        return None
    if not backup_dir:
        logger.warning("SQLite database backups disabled; SVC_DB_BACKUP_DIR is not set")
        return None

    worker = DatabaseBackupWorker(interval_hours=interval_hours, backup_dir=backup_dir)
    worker.start()
    logger.info(
        "SQLite database backups enabled every %.3g hour(s) to %s",
        interval_hours,
        backup_dir,
    )
    return worker
