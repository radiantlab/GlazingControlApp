from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def inspect_and_backup(data_dir: Path, backup_dir: Path) -> dict:
    if not data_dir.expanduser().is_absolute():
        raise ValueError("Production --data-dir must be an absolute path")
    if not backup_dir.expanduser().is_absolute():
        raise ValueError("Production --backup-dir must be an absolute path")
    data_dir = data_dir.expanduser().resolve(strict=True)
    database = data_dir / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(
            f"Production database not found at {database}; refusing to create an empty database"
        )

    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as source:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        table_names = [
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        table_counts = {
            name: source.execute(
                f'SELECT COUNT(*) FROM "{name.replace(chr(34), chr(34) * 2)}"'
            ).fetchone()[0]
            for name in table_names
        }

    backup_dir = backup_dir.expanduser().resolve(strict=False)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"production-audit-preflight-{stamp}.db"
    if destination.exists():
        raise FileExistsError(f"Backup already exists: {destination}")

    with sqlite3.connect(database) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    with sqlite3.connect(f"{destination.as_uri()}?mode=ro", uri=True) as backup:
        backup_integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
    if backup_integrity != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Backup integrity check failed: {backup_integrity}")

    return {
        "data_dir": str(data_dir),
        "database": str(database),
        "database_bytes": database.stat().st_size,
        "integrity": integrity,
        "table_counts": table_counts,
        "backup": str(destination),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify and back up the existing production SQLite database."
    )
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_and_backup(args.data_dir, args.backup_dir), indent=2))


if __name__ == "__main__":
    main()
