from __future__ import annotations
import json
import os
import time
import sqlite3
from typing import Dict, List, Tuple, Any
from .models import Panel, Group, Snapshot, AuditEntry
from .config import PANELS_FILE, PANELS_CONFIG_FILE, PANELS_STATE_FILE, AUDIT_FILE, AUDIT_DB_FILE


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(PANELS_CONFIG_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(PANELS_STATE_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    # AUDIT_DB_FILE lives in the same directory as AUDIT_FILE so no extra work needed


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
        "groups": data.get("groups", {}),
    }

    # Write config file
    with open(PANELS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    # Extract state (runtime values)
    state_data = {}
    for panel_id, panel_data in data.get("panels", {}).items():
        state_data[panel_id] = {
            "level": panel_data.get("level", 0),
            "last_change_ts": panel_data.get("last_change_ts", 0.0),
        }
    
    # Write state to both SQLite database and JSON file
    _ensure_panel_state_db()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        for panel_id, state in state_data.items():
            cur.execute(
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
    finally:
        conn.close()
    
    # Also write JSON file for backward compatibility
    with open(PANELS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)


def load_config() -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
    """Load panel and group configuration (structure only)."""
    _ensure_dirs()
    _migrate_from_legacy_panels_json()

    if not os.path.exists(PANELS_CONFIG_FILE):
        return {}, {}

    with open(PANELS_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("panels", {}), data.get("groups", {})


def load_state() -> Dict[str, Dict]:
    """Load panel runtime state (level, last_change_ts) from SQLite database."""
    _ensure_dirs()
    _migrate_from_legacy_panels_json()
    _ensure_panel_state_db()
    _migrate_json_state_to_db()

    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute("SELECT panel_id, level, last_change_ts FROM panel_state")
        rows = cur.fetchall()
        
        state_data = {}
        for row in rows:
            panel_id, level, last_change_ts = row
            state_data[panel_id] = {
                "level": level,
                "last_change_ts": last_change_ts,
            }
        
        return state_data
    finally:
        conn.close()


def load_snapshot() -> Snapshot:
    """Load complete snapshot by merging config and state."""
    config_panels, config_groups = load_config()
    state_data = load_state()

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

    groups = {k: Group(**v) for k, v in config_groups.items()}
    return Snapshot(panels=panels, groups=groups)


def save_config(panels: Dict[str, Panel], groups: Dict[str, Group]) -> None:
    """Save panel and group configuration (structure only)."""
    _ensure_dirs()
    config_panels = {}
    for panel_id, panel in panels.items():
        config_panels[panel_id] = {
            "id": panel.id,
            "name": panel.name,
            "group_id": panel.group_id,
        }

    config_groups = {k: v.model_dump() for k, v in groups.items()}

    config_data = {
        "panels": config_panels,
        "groups": config_groups,
    }

    with open(PANELS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


def save_state(panels: Dict[str, Panel]) -> None:
    """Save panel runtime state (level, last_change_ts) to both SQLite database and JSON file."""
    _ensure_dirs()
    _ensure_panel_state_db()
    
    # Prepare state data
    state_data = {}
    for panel_id, panel in panels.items():
        state_data[panel_id] = {
            "level": panel.level,
            "last_change_ts": panel.last_change_ts,
        }
    
    # Write to SQLite database
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        for panel_id, state in state_data.items():
            cur.execute(
                """
                INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
                VALUES (?, ?, ?)
                """,
                (panel_id, state["level"], state["last_change_ts"]),
            )
        conn.commit()
    finally:
        conn.close()
    
    # Also write to JSON file for backward compatibility during transition
    with open(PANELS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)


def update_panel_state(panel_id: str, level: int) -> None:
    """
    Update a single panel's state (level and last_change_ts) in both SQLite database 
    and JSON file when a successful command is received.
    This keeps the displayed tint level accurate based on successful API responses.
    """
    _ensure_dirs()
    _migrate_from_legacy_panels_json()
    _ensure_panel_state_db()
    _migrate_json_state_to_db()
    
    last_change_ts = time.time()
    
    # Update SQLite database
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO panel_state (panel_id, level, last_change_ts)
            VALUES (?, ?, ?)
            """,
            (panel_id, level, last_change_ts),
        )
        conn.commit()
    finally:
        conn.close()
    
    # Also update JSON file for backward compatibility during transition
    if os.path.exists(PANELS_STATE_FILE):
        with open(PANELS_STATE_FILE, "r", encoding="utf-8") as f:
            state_data = json.load(f)
    else:
        state_data = {}
    state_data[panel_id] = {
        "level": level,
        "last_change_ts": last_change_ts,
    }
    with open(PANELS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)


def save_snapshot(s: Snapshot) -> None:
    """Save snapshot by writing config and state separately."""
    save_config(s.panels, s.groups)
    save_state(s.panels)


def _ensure_audit_db() -> None:
    """Create the SQLite database and table for audit logs if they do not exist."""
    _ensure_dirs()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
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
        conn.commit()
    finally:
        conn.close()


def _ensure_panel_state_db() -> None:
    """Create the SQLite table for panel states if it does not exist."""
    _ensure_dirs()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_state (
                panel_id TEXT PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 0,
                last_change_ts REAL NOT NULL DEFAULT 0.0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_json_state_to_db() -> None:
    """Migrate panel state from JSON file to SQLite database if JSON exists and DB is empty."""
    _ensure_panel_state_db()
    
    # Check if JSON file exists
    if not os.path.exists(PANELS_STATE_FILE):
        return
    
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        # Check if DB already has panel states
        cur.execute("SELECT COUNT(*) FROM panel_state")
        count = cur.fetchone()[0]
        if count > 0:
            # Already migrated, skip
            return
        
        # Load JSON state
        with open(PANELS_STATE_FILE, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        
        # Insert into database
        for panel_id, state in state_data.items():
            cur.execute(
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
    finally:
        conn.close()


def append_audit(entry: AuditEntry) -> None:
    """Append audit entry to JSON file and SQLite database."""
    _ensure_dirs()
    row = entry.model_dump()
    # write one JSON per line for easy tailing
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    # also mirror into SQLite
    _ensure_audit_db()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(
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
        conn.commit()
    finally:
        conn.close()


def fetch_audit_entries(limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetch audit entries from SQLite ordered newest first."""
    _ensure_audit_db()
    conn = sqlite3.connect(AUDIT_DB_FILE)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, actor, target_type, target_id, level, applied_to, result
            FROM audit_log
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
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
    finally:
        conn.close()



def bootstrap_default_if_empty() -> Snapshot:
    """Bootstrap default panels and groups if config doesn't exist."""
    snap = load_snapshot()
    if snap.panels:
        return snap

    # Default configuration: 18 facade panels and 2 skylights (20 total)
    for i in range(1, 19):
        pid = f"P{i:02d}"
        snap.panels[pid] = Panel(id=pid, name=f"Facade {i}", group_id="G-facade")
    snap.panels["SK1"] = Panel(id="SK1", name="Skylight 1", group_id="G-skylights")
    snap.panels["SK2"] = Panel(id="SK2", name="Skylight 2", group_id="G-skylights")
    snap.groups["G-facade"] = Group(
        id="G-facade",
        name="Facade",
        member_ids=[f"P{i:02d}" for i in range(1, 19)],
    )
    snap.groups["G-skylights"] = Group(
        id="G-skylights",
        name="Skylights",
        member_ids=["SK1", "SK2"],
    )
    # Save both config and state (newly created panels default to level=0, last_change_ts=0.0)
    save_snapshot(snap)
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
