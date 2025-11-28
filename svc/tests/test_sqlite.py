"""
Comprehensive tests for SQLite database operations.

Tests cover:
- Database context manager
- Audit log operations (append, fetch, pagination)
- Panel state operations (save, load, update)
- Database initialization
- Migration from JSON to SQLite
"""
import os
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Dict

import pytest

from app.models import AuditEntry, Panel
from app.state import (
    _db_connection,
    _ensure_audit_db,
    _ensure_panel_state_db,
    _migrate_json_state_to_db,
    append_audit,
    fetch_audit_entries,
    load_state,
    save_state,
    update_panel_state,
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database file for testing."""
    db_file = tmp_path / "test_audit.db"
    monkeypatch.setattr("app.state.AUDIT_DB_FILE", str(db_file))
    monkeypatch.setattr("app.config.AUDIT_DB_FILE", str(db_file))
    
    # Clean up any existing database
    if db_file.exists():
        db_file.unlink()
    
    yield str(db_file)
    
    # Cleanup
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def temp_state_file(tmp_path, monkeypatch):
    """Create a temporary state file for testing."""
    state_file = tmp_path / "test_panels_state.json"
    config_file = tmp_path / "test_panels_config.json"
    legacy_file = tmp_path / "test_panels.json"
    
    # Patch all file paths to use temp directory
    monkeypatch.setattr("app.state.PANELS_STATE_FILE", str(state_file))
    monkeypatch.setattr("app.config.PANELS_STATE_FILE", str(state_file))
    monkeypatch.setattr("app.state.PANELS_CONFIG_FILE", str(config_file))
    monkeypatch.setattr("app.config.PANELS_CONFIG_FILE", str(config_file))
    monkeypatch.setattr("app.state.PANELS_FILE", str(legacy_file))
    monkeypatch.setattr("app.config.PANELS_FILE", str(legacy_file))
    
    yield str(state_file)
    
    # Cleanup
    if Path(state_file).exists():
        Path(state_file).unlink()
    if Path(config_file).exists():
        Path(config_file).unlink()
    if Path(legacy_file).exists():
        Path(legacy_file).unlink()


class TestDatabaseContextManager:
    """Tests for the _db_connection context manager."""
    
    def test_context_manager_creates_connection(self, temp_db):
        """Context manager should create and close connection."""
        with _db_connection() as conn:
            assert conn is not None
            assert isinstance(conn, sqlite3.Connection)
            # Connection should be open
            assert conn.execute("SELECT 1").fetchone()[0] == 1
        
        # Connection should be closed after context exits
        # (We can't directly test this, but if it wasn't closed, we'd get errors)
    
    def test_context_manager_commits_on_success(self, temp_db):
        """Context manager should commit transactions on success."""
        _ensure_audit_db()
        
        with _db_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, actor, target_type, target_id, level, applied_to, result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), "test", "panel", "P01", 50, "[]", "test"),
            )
        
        # Verify data was committed by opening a new connection
        with _db_connection() as conn:
            rows = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            assert rows[0] == 1
    
    def test_context_manager_rolls_back_on_error(self, temp_db):
        """Context manager should rollback transactions on error."""
        _ensure_audit_db()
        
        try:
            with _db_connection() as conn:
                conn.execute(
                    "INSERT INTO audit_log (ts, actor, target_type, target_id, level, applied_to, result) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (time.time(), "test", "panel", "P01", 50, "[]", "test"),
                )
                # Force an error
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Verify data was NOT committed
        with _db_connection() as conn:
            rows = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            assert rows[0] == 0
    
    def test_context_manager_with_row_factory(self, temp_db):
        """Context manager should support row_factory parameter."""
        _ensure_audit_db()
        
        with _db_connection(row_factory=sqlite3.Row) as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, actor, target_type, target_id, level, applied_to, result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), "test", "panel", "P01", 50, "[]", "test"),
            )
            
            rows = conn.execute("SELECT * FROM audit_log").fetchall()
            assert len(rows) == 1
            # With Row factory, we can access by column name
            assert rows[0]["actor"] == "test"
            assert rows[0]["target_id"] == "P01"


class TestAuditLogOperations:
    """Tests for audit log database operations."""
    
    def test_append_audit_creates_entry(self, temp_db):
        """append_audit should create an audit log entry."""
        entry = AuditEntry(
            ts=time.time(),
            actor="test_actor",
            target_type="panel",
            target_id="P01",
            level=50,
            applied_to=["P01"],
            result="test result",
        )
        
        append_audit(entry)
        
        # Verify entry was created
        entries = fetch_audit_entries()
        assert len(entries) == 1
        assert entries[0]["actor"] == "test_actor"
        assert entries[0]["target_id"] == "P01"
        assert entries[0]["level"] == 50
        assert entries[0]["applied_to"] == ["P01"]
        assert entries[0]["result"] == "test result"
    
    def test_append_audit_handles_empty_applied_to(self, temp_db):
        """append_audit should handle empty applied_to list."""
        entry = AuditEntry(
            ts=time.time(),
            actor="test",
            target_type="panel",
            target_id="P01",
            level=50,
            applied_to=[],
            result="dwell time not met",
        )
        
        append_audit(entry)
        
        entries = fetch_audit_entries()
        assert len(entries) == 1
        assert entries[0]["applied_to"] == []
    
    def test_append_audit_handles_multiple_applied_to(self, temp_db):
        """append_audit should handle multiple panels in applied_to."""
        entry = AuditEntry(
            ts=time.time(),
            actor="test",
            target_type="group",
            target_id="G-facade",
            level=75,
            applied_to=["P01", "P02", "P03"],
            result="group updated",
        )
        
        append_audit(entry)
        
        entries = fetch_audit_entries()
        assert len(entries) == 1
        assert entries[0]["applied_to"] == ["P01", "P02", "P03"]
    
    def test_fetch_audit_entries_orders_newest_first(self, temp_db):
        """fetch_audit_entries should return entries ordered newest first."""
        # Create entries with different timestamps
        base_time = time.time()
        for i in range(5):
            entry = AuditEntry(
                ts=base_time + i,
                actor="test",
                target_type="panel",
                target_id=f"P{i:02d}",
                level=50,
                applied_to=[],
                result="test",
            )
            append_audit(entry)
        
        entries = fetch_audit_entries()
        assert len(entries) == 5
        
        # Verify ordering (newest first)
        timestamps = [e["ts"] for e in entries]
        assert timestamps == sorted(timestamps, reverse=True)
    
    def test_fetch_audit_entries_with_limit(self, temp_db):
        """fetch_audit_entries should respect limit parameter."""
        # Create 10 entries
        base_time = time.time()
        for i in range(10):
            entry = AuditEntry(
                ts=base_time + i,
                actor="test",
                target_type="panel",
                target_id=f"P{i:02d}",
                level=50,
                applied_to=[],
                result="test",
            )
            append_audit(entry)
        
        # Fetch with limit
        entries = fetch_audit_entries(limit=5)
        assert len(entries) == 5
    
    def test_fetch_audit_entries_with_offset(self, temp_db):
        """fetch_audit_entries should respect offset parameter."""
        # Create 10 entries
        base_time = time.time()
        for i in range(10):
            entry = AuditEntry(
                ts=base_time + i,
                actor="test",
                target_type="panel",
                target_id=f"P{i:02d}",
                level=50,
                applied_to=[],
                result="test",
            )
            append_audit(entry)
        
        # Fetch first 5
        first_batch = fetch_audit_entries(limit=5, offset=0)
        # Fetch next 5
        second_batch = fetch_audit_entries(limit=5, offset=5)
        
        assert len(first_batch) == 5
        assert len(second_batch) == 5
        # Verify no overlap
        first_ids = {e["target_id"] for e in first_batch}
        second_ids = {e["target_id"] for e in second_batch}
        assert first_ids.isdisjoint(second_ids)
    
    def test_fetch_audit_entries_handles_invalid_json(self, temp_db):
        """fetch_audit_entries should handle invalid JSON in applied_to gracefully."""
        # Manually insert entry with invalid JSON
        _ensure_audit_db()
        with _db_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, actor, target_type, target_id, level, applied_to, result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (time.time(), "test", "panel", "P01", 50, "invalid json", "test"),
            )
        
        entries = fetch_audit_entries()
        assert len(entries) == 1
        # Should default to empty list on JSON parse error
        assert entries[0]["applied_to"] == []


class TestPanelStateOperations:
    """Tests for panel state database operations."""
    
    def test_save_state_creates_panel_states(self, temp_db, temp_state_file):
        """save_state should create panel state entries."""
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
            "P02": Panel(id="P02", name="Panel 2", level=75, last_change_ts=time.time()),
        }
        
        save_state(panels)
        
        # Verify states were saved
        state_data = load_state()
        assert len(state_data) == 2
        assert state_data["P01"]["level"] == 50
        assert state_data["P02"]["level"] == 75
    
    def test_save_state_updates_existing_panels(self, temp_db, temp_state_file):
        """save_state should update existing panel states."""
        # Create initial state
        panels1 = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
        }
        save_state(panels1)
        
        # Update state
        panels2 = {
            "P01": Panel(id="P01", name="Panel 1", level=75, last_change_ts=time.time()),
        }
        save_state(panels2)
        
        # Verify update
        state_data = load_state()
        assert state_data["P01"]["level"] == 75
    
    def test_load_state_returns_empty_dict_when_no_data(self, temp_db, temp_state_file):
        """load_state should return empty dict when no panel states exist."""
        state_data = load_state()
        assert isinstance(state_data, dict)
        assert len(state_data) == 0
    
    def test_load_state_returns_all_panels(self, temp_db, temp_state_file):
        """load_state should return all panel states."""
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=100.0),
            "P02": Panel(id="P02", name="Panel 2", level=75, last_change_ts=200.0),
            "P03": Panel(id="P03", name="Panel 3", level=25, last_change_ts=300.0),
        }
        save_state(panels)
        
        state_data = load_state()
        assert len(state_data) == 3
        assert state_data["P01"]["level"] == 50
        assert state_data["P01"]["last_change_ts"] == 100.0
        assert state_data["P02"]["level"] == 75
        assert state_data["P03"]["level"] == 25
    
    def test_update_panel_state_updates_single_panel(self, temp_db, temp_state_file):
        """update_panel_state should update a single panel's state."""
        # Create initial state
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
        }
        save_state(panels)
        
        # Update single panel
        update_panel_state("P01", 75)
        
        # Verify update
        state_data = load_state()
        assert state_data["P01"]["level"] == 75
        assert state_data["P01"]["last_change_ts"] > time.time() - 1  # Should be recent
    
    def test_update_panel_state_creates_new_panel(self, temp_db, temp_state_file):
        """update_panel_state should create state for new panel."""
        update_panel_state("P99", 50)
        
        state_data = load_state()
        assert "P99" in state_data
        assert state_data["P99"]["level"] == 50


class TestDatabaseInitialization:
    """Tests for database initialization functions."""
    
    def test_ensure_audit_db_creates_table(self, temp_db):
        """_ensure_audit_db should create audit_log table."""
        _ensure_audit_db()
        
        # Verify table exists and has correct schema
        with _db_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
            )
            assert cursor.fetchone() is not None
            
            # Verify schema
            cursor = conn.execute("PRAGMA table_info(audit_log)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "id" in columns
            assert "ts" in columns
            assert "actor" in columns
            assert "target_type" in columns
            assert "target_id" in columns
            assert "level" in columns
            assert "applied_to" in columns
            assert "result" in columns
    
    def test_ensure_audit_db_is_idempotent(self, temp_db):
        """_ensure_audit_db should be safe to call multiple times."""
        _ensure_audit_db()
        _ensure_audit_db()  # Call again
        
        # Should not error and table should still exist
        with _db_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
            )
            assert cursor.fetchone() is not None
    
    def test_ensure_panel_state_db_creates_table(self, temp_db):
        """_ensure_panel_state_db should create panel_state table."""
        _ensure_panel_state_db()
        
        # Verify table exists and has correct schema
        with _db_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='panel_state'"
            )
            assert cursor.fetchone() is not None
            
            # Verify schema
            cursor = conn.execute("PRAGMA table_info(panel_state)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            assert "panel_id" in columns
            assert "level" in columns
            assert "last_change_ts" in columns
    
    def test_ensure_panel_state_db_is_idempotent(self, temp_db):
        """_ensure_panel_state_db should be safe to call multiple times."""
        _ensure_panel_state_db()
        _ensure_panel_state_db()  # Call again
        
        # Should not error and table should still exist
        with _db_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='panel_state'"
            )
            assert cursor.fetchone() is not None


class TestMigration:
    """Tests for JSON to SQLite migration."""
    
    def test_migrate_json_state_to_db_migrates_data(self, temp_db, temp_state_file):
        """_migrate_json_state_to_db should migrate JSON data to SQLite."""
        # Create JSON state file
        json_data = {
            "P01": {"level": 50, "last_change_ts": 100.0},
            "P02": {"level": 75, "last_change_ts": 200.0},
        }
        with open(temp_state_file, "w") as f:
            json.dump(json_data, f)
        
        # Migrate
        _migrate_json_state_to_db()
        
        # Verify data was migrated
        state_data = load_state()
        assert len(state_data) == 2
        assert state_data["P01"]["level"] == 50
        assert state_data["P01"]["last_change_ts"] == 100.0
        assert state_data["P02"]["level"] == 75
    
    def test_migrate_json_state_to_db_skips_if_no_json_file(self, temp_db, temp_state_file):
        """_migrate_json_state_to_db should skip if JSON file doesn't exist."""
        # Ensure JSON file doesn't exist
        if Path(temp_state_file).exists():
            Path(temp_state_file).unlink()
        
        # Should not error
        _migrate_json_state_to_db()
        
        # Database should be empty
        state_data = load_state()
        assert len(state_data) == 0
    
    def test_migrate_json_state_to_db_skips_if_db_has_data(self, temp_db, temp_state_file):
        """_migrate_json_state_to_db should skip if database already has data."""
        # Create initial state in database
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
        }
        save_state(panels)
        
        # Create JSON file with different data
        json_data = {
            "P02": {"level": 75, "last_change_ts": 200.0},
        }
        with open(temp_state_file, "w") as f:
            json.dump(json_data, f)
        
        # Migrate should skip
        _migrate_json_state_to_db()
        
        # Original data should still be there, new data should not be migrated
        state_data = load_state()
        assert "P01" in state_data
        assert "P02" not in state_data


class TestIntegration:
    """Integration tests for SQLite operations."""
    
    def test_audit_and_state_operations_together(self, temp_db, temp_state_file):
        """Test that audit and state operations work together."""
        # Create panel state
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
        }
        save_state(panels)
        
        # Create audit entry
        entry = AuditEntry(
            ts=time.time(),
            actor="test",
            target_type="panel",
            target_id="P01",
            level=75,
            applied_to=["P01"],
            result="panel updated",
        )
        append_audit(entry)
        
        # Verify both work
        state_data = load_state()
        assert state_data["P01"]["level"] == 50  # State not updated by audit
        
        entries = fetch_audit_entries()
        assert len(entries) == 1
        assert entries[0]["target_id"] == "P01"
    
    def test_multiple_operations_in_sequence(self, temp_db, temp_state_file):
        """Test multiple operations in sequence."""
        # Save state
        panels = {
            "P01": Panel(id="P01", name="Panel 1", level=50, last_change_ts=time.time()),
        }
        save_state(panels)
        
        # Update state
        update_panel_state("P01", 75)
        
        # Create audit entry
        entry = AuditEntry(
            ts=time.time(),
            actor="test",
            target_type="panel",
            target_id="P01",
            level=75,
            applied_to=["P01"],
            result="panel updated",
        )
        append_audit(entry)
        
        # Verify final state
        state_data = load_state()
        assert state_data["P01"]["level"] == 75
        
        entries = fetch_audit_entries()
        assert len(entries) == 1

