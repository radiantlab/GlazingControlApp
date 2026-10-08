from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import routes
from app.models import SensorIngestBatch, SensorIngestEvent
from app.state import (
    UnknownSensorError,
    fetch_sensor_ingest_status,
    fetch_latest_spectrum,
    ingest_sensor_events,
    prune_sensors_to_ids,
    register_sensor,
)
from main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "sensor-ingest.db"
    monkeypatch.setattr("app.state.AUDIT_DB_FILE", str(db_file))
    monkeypatch.setattr("app.config.AUDIT_DB_FILE", str(db_file))
    monkeypatch.setattr(routes, "SENSOR_INGEST_TOKEN", "")
    yield db_file


def _event(
    *,
    event_id: str = "collector:T10A1-H1:1720000000000",
    sensor_id: str = "T10A1-H1",
) -> dict:
    return {
        "event_id": event_id,
        "sensor_id": sensor_id,
        "observed_ts": 1_720_000_000.125,
        "metrics": {"lux": 321.5, "temperature_c": 22.75},
        "source": "windows-host:COM4",
    }


def _row_count(db_file, table: str) -> int:
    with sqlite3.connect(db_file) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_endpoint_is_disabled_when_token_is_empty() -> None:
    response = client.post("/sensors/ingest", json={"events": [_event()]})

    assert response.status_code == 404
    assert response.json()["detail"] == "Sensor ingestion is disabled"


def test_endpoint_uses_constant_time_token_check(monkeypatch) -> None:
    monkeypatch.setattr(routes, "SENSOR_INGEST_TOKEN", "expected")
    calls: list[tuple[str, str]] = []

    def compare_digest(provided: str, expected: str) -> bool:
        calls.append((provided, expected))
        return False

    monkeypatch.setattr(routes.secrets, "compare_digest", compare_digest)

    response = client.post(
        "/sensors/ingest",
        headers={"X-Sensor-Ingest-Token": "wrong"},
        json={"events": [_event()]},
    )

    assert response.status_code == 401
    assert calls == [("wrong", "expected")]


def test_ingestion_is_atomic_and_idempotent(temp_db, monkeypatch) -> None:
    register_sensor("T10A1-H1", "t10a", "T-10A head 1", None, {})
    monkeypatch.setattr(routes, "SENSOR_INGEST_TOKEN", "expected")
    payload = {"events": [_event()]}

    first = client.post(
        "/sensors/ingest",
        headers={"X-Sensor-Ingest-Token": "expected"},
        json=payload,
    )
    retry = client.post(
        "/sensors/ingest",
        headers={"X-Sensor-Ingest-Token": "expected"},
        json=payload,
    )

    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0}
    assert retry.status_code == 200
    assert retry.json() == {"accepted": 0, "duplicates": 1}
    assert _row_count(temp_db, "sensor_ingest_events") == 1
    assert _row_count(temp_db, "sensor_readings") == 2


def test_same_observation_from_another_source_is_a_duplicate(temp_db) -> None:
    # Switching acquisition from the Windows agent to the embedded watcher
    # re-reads the same capture under a different event-ID namespace.
    register_sensor("T10A1-H1", "t10a", "T-10A head 1", None, {})
    agent_event = SensorIngestEvent.model_validate(_event())
    container_event = SensorIngestEvent.model_validate(
        {**_event(event_id="container:T10A1-H1:abc"), "source": "container:T10A1-H1"}
    )

    assert ingest_sensor_events([agent_event]) == (1, 0)
    assert ingest_sensor_events([container_event]) == (0, 1)
    assert _row_count(temp_db, "sensor_ingest_events") == 1
    assert _row_count(temp_db, "sensor_readings") == 2


def test_unknown_sensor_rejects_entire_batch(temp_db) -> None:
    register_sensor("T10A1-H1", "t10a", "T-10A head 1", None, {})
    events = [
        SensorIngestEvent(**_event(event_id="known")),
        SensorIngestEvent(**_event(event_id="unknown", sensor_id="NOT-CONFIGURED")),
    ]

    with pytest.raises(UnknownSensorError, match="NOT-CONFIGURED"):
        ingest_sensor_events(events)

    assert _row_count(temp_db, "sensor_ingest_events") == 0
    assert _row_count(temp_db, "sensor_readings") == 0


def test_inactive_sensor_rejects_entire_batch(temp_db) -> None:
    register_sensor("T10A1-H1", "t10a", "T-10A head 1", None, {})
    register_sensor("OLD-00", "t10a", "Removed head", None, {})
    prune_sensors_to_ids(["T10A1-H1"])
    events = [
        SensorIngestEvent(**_event(event_id="known")),
        SensorIngestEvent(
            **_event(event_id="inactive", sensor_id="OLD-00")
        ),
    ]

    with pytest.raises(UnknownSensorError, match="OLD-00"):
        ingest_sensor_events(events)

    assert _row_count(temp_db, "sensor_ingest_events") == 0
    assert _row_count(temp_db, "sensor_readings") == 0


def test_spectrum_is_written_with_observation(temp_db) -> None:
    register_sensor("JETI-00", "jeti", "JETI", None, {})
    event = SensorIngestEvent(
        **{
            **_event(event_id="jeti:sample-1", sensor_id="JETI-00"),
            "spectrum": [1.0, 2.0, 3.0],
            "spectrum_wavelength_start": 400,
            "spectrum_wavelength_step": 2,
        }
    )

    assert ingest_sensor_events([event]) == (1, 0)
    spectrum = fetch_latest_spectrum("JETI-00")

    assert spectrum is not None
    assert spectrum["values"] == [1.0, 2.0, 3.0]
    assert spectrum["wavelength_start"] == 400
    assert spectrum["wavelength_end"] == 404
    assert spectrum["wavelength_step"] == 2


def test_ingest_status_reports_last_event_for_active_sensors() -> None:
    register_sensor("EKO-00", "eko", "EKO", None, {})
    register_sensor("T10A1-H1", "t10a", "T-10A", None, {})
    register_sensor("OLD-00", "t10a", "Inactive", None, {})
    ingest_sensor_events(
        [
            SensorIngestEvent(**_event(event_id="first")),
            SensorIngestEvent(
                **{
                    **_event(event_id="second"),
                    "observed_ts": 1_720_000_001.0,
                    "source": "windows-host:COM5",
                }
            ),
            SensorIngestEvent(
                **_event(event_id="inactive-event", sensor_id="OLD-00")
            ),
        ]
    )
    prune_sensors_to_ids(["EKO-00", "T10A1-H1"])

    status = fetch_sensor_ingest_status()

    assert status == [
        {
            "sensor_id": "EKO-00",
            "event_id": None,
            "observed_ts": None,
            "received_ts": None,
            "source": None,
            "stale_after_s": 180.0,
        },
        {
            "sensor_id": "T10A1-H1",
            "event_id": "second",
            "observed_ts": 1_720_000_001.0,
            "received_ts": status[1]["received_ts"],
            "source": "windows-host:COM5",
            "stale_after_s": 180.0,
        },
    ]
    assert status[1]["received_ts"] is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("observed_ts", float("nan")),
        ("observed_ts", float("inf")),
        ("metrics", {"lux": float("-inf")}),
        ("spectrum", [1.0, float("nan")]),
    ],
)
def test_nonfinite_observation_data_is_rejected(field, value) -> None:
    payload = _event()
    payload[field] = value

    with pytest.raises(ValidationError):
        SensorIngestBatch(events=[payload])
