import json
import pytest
from fastapi.testclient import TestClient
from main import app
from app.state import register_sensor, list_sensors
from app.sensors import manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database and config file for testing."""
    db_file = tmp_path / "test_audit.db"
    monkeypatch.setattr("app.state.AUDIT_DB_FILE", str(db_file))
    monkeypatch.setattr("app.config.AUDIT_DB_FILE", str(db_file))
    
    config_file = tmp_path / "sensors_config.json"
    dummy_config = {
        "t10a": [
            {
                "device_id": "KM1",
                "port": "COM3",
                "interval_s": 60,
                "heads": [
                    {"head_no": 0, "sensor_id": "T10A1-H1", "label": "T-10A #1 Head 1"},
                    {"head_no": 1, "sensor_id": "T10A1-H2", "label": "T-10A #1 Head 2"}
                ]
            }
        ]
    }
    config_file.write_text(json.dumps(dummy_config), encoding="utf-8")
    monkeypatch.setattr(manager, "_get_sensors_config_file", lambda: str(config_file))
    
    if db_file.exists():
        db_file.unlink()
    
    yield str(db_file)
    
    if db_file.exists():
        db_file.unlink()


def test_update_sensor_labels_success():
    # Register sensors in the DB
    register_sensor(
        sensor_id="T10A1-H1",
        kind="t10a",
        label="T-10A #1 Head 1",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 0}
    )
    register_sensor(
        sensor_id="T10A1-H2",
        kind="t10a",
        label="T-10A #1 Head 2",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 1}
    )

    # Invoke update
    success = manager.update_sensor_labels(
        sensor_id="T10A1-H1",
        custom_label="Office Desk",
        device_custom_label="Main Body"
    )
    assert success is True

    # 1. Verify config file is NOT updated (labels remain untouched in sensors_config.json)
    config_path = manager._get_sensors_config_file()
    with open(config_path, "r") as f:
        cfg = json.load(f)
    
    dev = cfg["t10a"][0]
    assert "custom_label" not in dev
    assert "custom_label" not in dev["heads"][0]

    # 2. Verify database is updated
    db_sensors = list_sensors()
    h1 = next(s for s in db_sensors if s["id"] == "T10A1-H1")
    h2 = next(s for s in db_sensors if s["id"] == "T10A1-H2")

    assert h1["config"]["custom_label"] == "Office Desk"
    assert h1["config"]["device_custom_label"] == "Main Body"
    
    # Verify the body custom label cascaded to the other head belonging to the same device
    assert h2["config"]["device_custom_label"] == "Main Body"
    assert "custom_label" not in h2["config"]


def test_update_sensor_labels_clears_labels():
    register_sensor(
        sensor_id="T10A1-H1",
        kind="t10a",
        label="T-10A #1 Head 1",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 0, "custom_label": "Office Desk", "device_custom_label": "Main Body"}
    )
    
    # Invoke update with empty strings to clear labels
    success = manager.update_sensor_labels(
        sensor_id="T10A1-H1",
        custom_label="",
        device_custom_label=""
    )
    assert success is True

    # 1. Verify config file is NOT updated (labels remain untouched/empty in sensors_config.json)
    config_path = manager._get_sensors_config_file()
    with open(config_path, "r") as f:
        cfg = json.load(f)
    assert "custom_label" not in cfg["t10a"][0]
    assert "custom_label" not in cfg["t10a"][0]["heads"][0]

    # 2. Verify database is updated (keys popped)
    db_sensors = list_sensors()
    h1 = next(s for s in db_sensors if s["id"] == "T10A1-H1")
    assert "custom_label" not in h1["config"]
    assert "device_custom_label" not in h1["config"]


def test_register_sensor_preserves_database_custom_labels():
    # 1. Register a sensor
    register_sensor(
        sensor_id="T10A1-H1",
        kind="t10a",
        label="T-10A #1 Head 1",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 0}
    )
    
    # 2. Update its labels
    success = manager.update_sensor_labels(
        sensor_id="T10A1-H1",
        custom_label="Office Desk",
        device_custom_label="Main Body"
    )
    assert success is True
    
    # 3. Simulate startup/reload by reregistering the sensor with clean config (as loaded from file)
    register_sensor(
        sensor_id="T10A1-H1",
        kind="t10a",
        label="T-10A #1 Head 1",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 0}
    )
    
    # 4. Verify custom labels are still preserved in the database config
    db_sensors = list_sensors()
    h1 = next(s for s in db_sensors if s["id"] == "T10A1-H1")
    assert h1["config"]["custom_label"] == "Office Desk"
    assert h1["config"]["device_custom_label"] == "Main Body"


def test_patch_sensor_labels_api_endpoint():
    # Register sensors in the DB
    register_sensor(
        sensor_id="T10A1-H1",
        kind="t10a",
        label="T-10A #1 Head 1",
        location=None,
        config={"device_id": "KM1", "port": "COM3", "head_no": 0}
    )

    response = client.patch(
        "/sensors/T10A1-H1",
        json={"custom_label": "Desk", "device_custom_label": "Body"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Verify invalid sensor ID yields 404
    response_404 = client.patch(
        "/sensors/NON-EXISTENT",
        json={"custom_label": "Desk"}
    )
    assert response_404.status_code == 404
