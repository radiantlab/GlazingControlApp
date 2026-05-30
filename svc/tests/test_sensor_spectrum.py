from fastapi.testclient import TestClient
import pytest
from app.sensors.jeti_spectraval_watcher import JetiSpectravalFileWatcher
from app.state import (
    delete_sensor_readings_for_ids,
    insert_sensor_reading,
    insert_sensor_spectrum,
    fetch_latest_spectrum,
    fetch_historical_spectrum,
    prune_sensors_to_ids,
    register_sensor,
)
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database file for testing."""
    db_file = tmp_path / "test_audit.db"
    monkeypatch.setattr("app.state.AUDIT_DB_FILE", str(db_file))
    monkeypatch.setattr("app.config.AUDIT_DB_FILE", str(db_file))
    
    if db_file.exists():
        db_file.unlink()
    
    yield str(db_file)
    
    if db_file.exists():
        db_file.unlink()


def test_sqlite_spectrum_operations():
    # Verify insert and fetch latest
    insert_sensor_spectrum("JETI-TEST", 1000.0, [1.0, 2.0, 3.0])
    latest = fetch_latest_spectrum("JETI-TEST")
    assert latest is not None
    assert latest["sensor_id"] == "JETI-TEST"
    assert latest["ts"] == 1000.0
    assert latest["wavelength_start"] == 380
    assert latest["wavelength_end"] == 382
    assert latest["wavelength_step"] == 1
    assert latest["values"] == [1.0, 2.0, 3.0]

    # Verify fetch historical close match
    hist = fetch_historical_spectrum("JETI-TEST", 1000.05)
    assert hist is not None
    assert hist["ts"] == 1000.0

    # Verify no match for far away timestamp
    hist_far = fetch_historical_spectrum("JETI-TEST", 1005.0)
    assert hist_far is None


def test_delete_sensor_readings_for_ids_removes_spectra():
    register_sensor("JETI-TEST", "jeti_spectraval", "JETI", None, {})
    insert_sensor_reading("JETI-TEST", 1000.0, "lux", 1.0)
    insert_sensor_spectrum("JETI-TEST", 1000.0, [1.0, 2.0, 3.0])

    delete_sensor_readings_for_ids(["JETI-TEST"])

    assert fetch_latest_spectrum("JETI-TEST") is None


def test_prune_sensors_to_ids_removes_spectra_for_pruned_sensors():
    register_sensor("JETI-KEEP", "jeti_spectraval", "JETI Keep", None, {})
    register_sensor("JETI-PRUNE", "jeti_spectraval", "JETI Prune", None, {})
    insert_sensor_spectrum("JETI-KEEP", 1000.0, [1.0, 2.0, 3.0])
    insert_sensor_spectrum("JETI-PRUNE", 1000.0, [4.0, 5.0, 6.0])

    prune_sensors_to_ids(["JETI-KEEP"])

    assert fetch_latest_spectrum("JETI-KEEP") is not None
    assert fetch_latest_spectrum("JETI-PRUNE") is None


def test_api_spectrum_endpoints():
    # Insert test data
    insert_sensor_spectrum("JETI-TEST", 2000.0, [10.0, 20.0, 30.0])

    # Latest endpoint
    response = client.get("/sensors/JETI-TEST/spectrum/latest")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["sensor_id"] == "JETI-TEST"
    assert res_data["ts"] == 2000.0
    assert res_data["values"] == [10.0, 20.0, 30.0]

    # Historical endpoint
    response_hist = client.get("/sensors/JETI-TEST/spectrum/historical?ts=2000.02")
    assert response_hist.status_code == 200
    res_hist_data = response_hist.json()
    assert res_hist_data["sensor_id"] == "JETI-TEST"
    assert res_hist_data["ts"] == 2000.0

    # Non-existent sensor / timestamp
    response_none = client.get("/sensors/NON-EXISTENT/spectrum/latest")
    assert response_none.status_code == 404


def test_watcher_yields_spectrum(tmp_path):
    output_dir = tmp_path / "jeti_output"
    output_dir.mkdir()
    cap_file = output_dir / "latest.cap"

    watcher = JetiSpectravalFileWatcher(
        device_id="JETI",
        sensor_id="JETI-00",
        input_path=str(cap_file),
        label="JETI",
        svc_root=str(tmp_path),
    )

    # Initial poll when file does not exist should be empty
    assert list(watcher.poll()) == []

    # Write data to the cap file
    cap_file.write_text(
        "Date and Time:; 11/18/2025; 08:49:54am; ; Ev [lx] (CIE1931 2°); 67.9; ; Spectral Values (380 nm - 1000 nm); 1.5; 2.5; 3.5\n",
        encoding="utf-8",
    )

    readings = list(watcher.poll())
    # Should yield standard metrics and a spectrum metric
    spec_readings = [r for r in readings if r.metric == "spectrum"]
    assert len(spec_readings) == 1
    assert spec_readings[0].spectrum == [1.5, 2.5, 3.5]
