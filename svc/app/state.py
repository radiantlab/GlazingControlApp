from __future__ import annotations
import json
import os
import time
import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Tuple, Any, Iterator, Optional, Callable
from .models import Panel, Group, Snapshot, AuditEntry
from .config import PANELS_FILE, PANELS_CONFIG_FILE, PANELS_STATE_FILE, AUDIT_DB_FILE


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(PANELS_CONFIG_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(PANELS_STATE_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(AUDIT_DB_FILE), exist_ok=True)


@contextmanager
def _db_connection(row_factory: Optional[Callable[[sqlite3.Cursor, tuple], Any]] = None) -> Iterator[sqlite3.Connection]:
    """
    Context manager for database connections.
    
    Automatically handles:
    - Connection creation and cleanup
    - Transaction commit on success
    - Transaction rollback on error
    
    Args:
        row_factory: Optional row factory (e.g., sqlite3.Row) to set on connection
    """
    _ensure_dirs()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    if row_factory:
        conn.row_factory = row_factory
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    """
    Initialize database and run all migrations once at application startup.
    
    This function should be called once when the application starts, not during
    runtime operations. It ensures:
    - Directories exist
    - Legacy JSON files are migrated
    - Database tables are created
    - JSON data is migrated to database (one-time)
    """
    _ensure_dirs()
    _migrate_from_legacy_panels_json()
    _ensure_panel_state_db()
    _ensure_groups_db()
    _migrate_json_state_to_db()
    _migrate_groups_json_to_db()


def _migrate_from_legacy_panels_json() -> None:
    """Migrate old panels.json to new separated config file and SQLite database."""
    if not os.path.exists(PANELS_FILE):
        return

    if os.path.exists(PANELS_CONFIG_FILE):
        # Already migrated, skip
        return

    _ensure_dirs()
    with open(PANELS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract config (structure)
    config_panels = {}
    for panel_id, panel_data in data.get("panels", {}).items():
        config_panels[panel_id] = {
            "id": panel_data["id"],
            "name": panel_data["name"],
            "group_id": panel_data.get("group_id"),
        }

    config_data = {
        "panels": config_panels,
    }

    # Write config file (panels only, groups go to DB)
    with open(PANELS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    
    # Migrate groups to database
    groups_data = data.get("groups", {})
    if groups_data:
        _ensure_groups_db()
        with _db_connection() as conn:
            for group_id, group_data in groups_data.items():
                if isinstance(group_data, dict):
                    conn.execute(
                        """
                        INSERT INTO groups (id, name, member_ids)
                        VALUES (?, ?, ?)
                        """,
                        (
                            group_id,
                            group_data.get("name", f"Group {group_id}"),
                            json.dumps(group_data.get("member_ids", [])),
                        ),
                    )

    # Extract state (runtime values)
    state_data = {}
    for panel_id, panel_data in data.get("panels", {}).items():
        state_data[panel_id] = {
            "level": panel_data.get("level", 0),
            "last_change_ts": panel_data.get("last_change_ts", 0.0),
        }
    
    # Write state to SQLite database
    _ensure_panel_state_db()
    with _db_connection() as conn:
        for panel_id, state in state_data.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
                VALUES (?, ?, ?)
                """,
                (
                    panel_id,
                    state.get("level", 0),
                    state.get("last_change_ts", 0.0),
                ),
            )


def load_config() -> Dict[str, Dict]:
    """Load panel configuration (structure only). Groups are now in database."""
    # Note: Legacy migration should be done at app startup via initialize_database()
    _ensure_dirs()

    if not os.path.exists(PANELS_CONFIG_FILE):
        return {}

    with open(PANELS_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("panels", {})


def load_state() -> Dict[str, Dict]:
    """Load panel runtime state (level, last_change_ts) from SQLite database."""
    _ensure_panel_state_db()  # Only ensure table exists, no migration

    with _db_connection() as conn:
        rows = conn.execute("SELECT panel_id, level, last_change_ts FROM panel_state").fetchall()
        
        state_data = {}
        for row in rows:
            panel_id, level, last_change_ts = row
            state_data[panel_id] = {
                "level": level,
                "last_change_ts": last_change_ts,
            }
        
        return state_data


def load_groups() -> Dict[str, Group]:
    """Load groups from SQLite database."""
    _ensure_groups_db()  # Only ensure table exists, no migration

    with _db_connection() as conn:
        rows = conn.execute("SELECT id, name, member_ids FROM groups").fetchall()
        
        groups = {}
        for row in rows:
            group_id, name, member_ids_json = row
            try:
                member_ids = json.loads(member_ids_json) if member_ids_json else []
            except Exception:
                member_ids = []
            groups[group_id] = Group(
                id=group_id,
                name=name,
                member_ids=member_ids,
            )
        
        return groups


def save_groups(groups: Dict[str, Group]) -> None:
    """Save groups to SQLite database."""
    _ensure_dirs()
    _ensure_groups_db()
    
    with _db_connection() as conn:
        # Delete all existing groups
        conn.execute("DELETE FROM groups")
        
        # Insert all groups
        for group_id, group in groups.items():
            conn.execute(
                """
                INSERT INTO groups (id, name, member_ids)
                VALUES (?, ?, ?)
                """,
                (group.id, group.name, json.dumps(group.member_ids)),
            )


def load_snapshot() -> Snapshot:
    """Load complete snapshot by merging config and state."""
    config_panels = load_config()
    state_data = load_state()
    groups = load_groups()

    # Merge config and state into Panel objects
    panels = {}
    for panel_id, panel_config in config_panels.items():
        panel_state = state_data.get(panel_id, {})
        panels[panel_id] = Panel(
            id=panel_config["id"],
            name=panel_config["name"],
            group_id=panel_config.get("group_id"),
            level=panel_state.get("level", 0),
            last_change_ts=panel_state.get("last_change_ts", 0.0),
        )

    return Snapshot(panels=panels, groups=groups)


def save_config(panels: Dict[str, Panel]) -> None:
    """Save panel configuration (structure only). Groups are now in database."""
    _ensure_dirs()
    config_panels = {}
    for panel_id, panel in panels.items():
        config_panels[panel_id] = {
            "id": panel.id,
            "name": panel.name,
            "group_id": panel.group_id,
        }

    config_data = {
        "panels": config_panels,
    }

    with open(PANELS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


def save_state(panels: Dict[str, Panel]) -> None:
    """Save panel runtime state (level, last_change_ts) to SQLite database."""
    _ensure_dirs()
    _ensure_panel_state_db()
    
    # Write to SQLite database
    with _db_connection() as conn:
        for panel_id, panel in panels.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
                VALUES (?, ?, ?)
                """,
                (panel_id, panel.level, panel.last_change_ts),
            )


def update_panel_state(panel_id: str, level: int) -> None:
    """
    Update a single panel's state (level and last_change_ts) in SQLite database 
    when a successful command is received.
    This keeps the displayed tint level accurate based on successful API responses.
    
    Note: Database initialization/migration should be done at app startup via initialize_database().
    """
    _ensure_panel_state_db()  # Only ensure table exists, no migration
    
    last_change_ts = time.time()
    
    # Update SQLite database
    with _db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
            VALUES (?, ?, ?)
            """,
            (panel_id, level, last_change_ts),
        )


def save_snapshot(s: Snapshot) -> None:
    """Save snapshot by writing config, state, and groups separately."""
    save_config(s.panels)
    save_state(s.panels)
    save_groups(s.groups)


def _ensure_audit_db() -> None:
    """Create the SQLite database and table for audit logs if they do not exist."""
    with _db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                actor TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                level INTEGER NOT NULL,
                applied_to TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )


def _ensure_panel_state_db() -> None:
    """Create the SQLite table for panel states if it does not exist."""
    with _db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_state (
                panel_id TEXT PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 0,
                last_change_ts REAL NOT NULL DEFAULT 0.0
            )
            """
        )


def _ensure_groups_db() -> None:
    """Create the SQLite table for groups if it does not exist."""
    with _db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                member_ids TEXT NOT NULL
            )
            """
        )


def _migrate_json_state_to_db() -> None:
    """Migrate panel state from JSON file to SQLite database if JSON exists and DB is empty."""
    _ensure_panel_state_db()
    
    # Check if JSON file exists
    if not os.path.exists(PANELS_STATE_FILE):
        return
    
    # Use the standard DB connection context manager for consistency
    with _db_connection() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Check if DB already has panel states
            count = conn.execute("SELECT COUNT(*) FROM panel_state").fetchone()[0]
            if count > 0:
                # Already migrated, skip
                conn.rollback()
                return

            # Load JSON state
            with open(PANELS_STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # Insert into database
            for panel_id, state in state_data.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
                    VALUES (?, ?, ?)
                    """,
                    (
                        panel_id,
                        state.get("level", 0),
                        state.get("last_change_ts", 0.0),
                    ),
                )
            conn.commit()
        except sqlite3.OperationalError:
            # Another process is already migrating or DB is locked
            conn.rollback()
        except (json.JSONDecodeError, IOError, OSError, Exception) as e:
            # Log error and rollback for any error during migration
            import logging
            logging.getLogger(__name__).warning(f"Failed to migrate panel state from JSON: {e}")
            conn.rollback()


def _migrate_groups_json_to_db() -> None:
    """Migrate groups from JSON file to SQLite database if JSON exists and DB is empty."""
    _ensure_groups_db()
    
    # Check if config file exists and has groups
    if not os.path.exists(PANELS_CONFIG_FILE):
        return
    
    # Use manual transaction handling for this special case that needs explicit rollback
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Check if DB already has groups
        count = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        if count > 0:
            # Already migrated, skip
            conn.rollback()
            return

        # Load JSON config
        with open(PANELS_CONFIG_FILE, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        groups_data = config_data.get("groups", {})
        if not groups_data:
            conn.rollback()
            return

        # Insert into database
        for group_id, group_data in groups_data.items():
            if isinstance(group_data, dict):
                conn.execute(
                    """
                    INSERT INTO groups (id, name, member_ids)
                    VALUES (?, ?, ?)
                    """,
                    (
                        group_id,
                        group_data.get("name", f"Group {group_id}"),
                        json.dumps(group_data.get("member_ids", [])),
                    ),
                )
        conn.commit()
    except sqlite3.OperationalError:
        # Another process is already migrating or DB is locked
        conn.rollback()
    except (json.JSONDecodeError, IOError, OSError, Exception) as e:
        # Log error and rollback for any error during migration
        import logging
        logging.getLogger(__name__).warning(f"Failed to migrate groups from JSON: {e}")
        conn.rollback()
    finally:
        conn.close()


def append_audit(entry: AuditEntry) -> None:
    """Append audit entry to SQLite database."""
    row = entry.model_dump()
    _ensure_audit_db()
    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (ts, actor, target_type, target_id, level, applied_to, result)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["ts"],
                row["actor"],
                row["target_type"],
                row["target_id"],
                row["level"],
                json.dumps(row["applied_to"]),
                row["result"],
            ),
        )


def fetch_audit_entries(limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetch audit entries from SQLite ordered newest first."""
    _ensure_audit_db()
    with _db_connection(row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            """
            SELECT ts, actor, target_type, target_id, level, applied_to, result
            FROM audit_log
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        
        result: List[Dict[str, Any]] = []
        for r in rows:
            row_dict = dict(r)
            # applied_to is stored as JSON text
            try:
                row_dict["applied_to"] = json.loads(row_dict.get("applied_to") or "[]")
            except Exception:
                row_dict["applied_to"] = []
            result.append(row_dict)
        return result



def bootstrap_default_if_empty() -> Snapshot:
    """
    Bootstrap default panels and groups if config doesn't exist.
    
    Only resets last_change_ts to 0.0 when actually creating new panels (initial bootstrap).
    On subsequent app starts, preserves existing timestamps to maintain dwell time protection.
    """
    snap = load_snapshot()
    created_new_panels = False
    needs_bootstrap = False
    
    # Check if we need to bootstrap panels
    if not snap.panels:
        created_new_panels = True
        needs_bootstrap = True
        # Default configuration: 18 facade panels and 2 skylights (20 total)
        # Set last_change_ts to 0.0 for newly created panels (initial bootstrap)
        for i in range(1, 19):
            pid = f"P{i:02d}"
            snap.panels[pid] = Panel(id=pid, name=f"Facade {i}", group_id="G-facade", last_change_ts=0.0)
        snap.panels["SK1"] = Panel(id="SK1", name="Skylight 1", group_id="G-skylights", last_change_ts=0.0)
        snap.panels["SK2"] = Panel(id="SK2", name="Skylight 2", group_id="G-skylights", last_change_ts=0.0)
    
    # Check if we need to bootstrap groups (even if panels exist)
    if not snap.groups or "G-facade" not in snap.groups or "G-skylights" not in snap.groups:
        needs_bootstrap = True
        # Ensure default groups exist
        if "G-facade" not in snap.groups:
            snap.groups["G-facade"] = Group(
                id="G-facade",
                name="Facade",
                member_ids=[f"P{i:02d}" for i in range(1, 19)],
            )
        if "G-skylights" not in snap.groups:
            snap.groups["G-skylights"] = Group(
                id="G-skylights",
                name="Skylights",
                member_ids=["SK1", "SK2"],
            )
    
    # Save if we made changes
    if needs_bootstrap:
        save_snapshot(snap)
    
    # Only reset timestamps if we actually created new panels (initial bootstrap)
    # This preserves dwell time protection on subsequent app starts
    if created_new_panels:
        default_panel_ids = [f"P{i:02d}" for i in range(1, 19)] + ["SK1", "SK2"]
        _ensure_panel_state_db()
        with _db_connection() as conn:
            for panel_id in default_panel_ids:
                # Reset last_change_ts to 0.0 only for newly created panels
                conn.execute(
                    """
                    INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
                    VALUES (?, 0, 0.0)
                    """,
                    (panel_id,),
                )
    
    return snap


def audit(
    actor: str,
    target_type: str,
    target_id: str,
    level: int,
    applied: List[str],
    result: str,
) -> None:
    append_audit(
        AuditEntry(
            ts=time.time(),
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            level=level,
            applied_to=applied,
            result=result,
        )
    )
