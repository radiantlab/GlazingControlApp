from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from app.config import Environment, SensorAcquisition
from app.sensors import manager
from app.sensors.interface import SensorReading
from app.sensors.serial_discovery import SerialPortInfo


def test_load_config_uses_environment_config_path(tmp_path, monkeypatch) -> None:
    repo_dir = tmp_path / "repo"
    svc_dir = repo_dir / "svc"
    data_dir = svc_dir / "data"
    data_dir.mkdir(parents=True)

    config_path = data_dir / "sensors_config.json"
    expected = {"t10a": [], "jeti_spectraval": [], "eko_ms90_plus": []}
    config_path.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.setattr(manager, "SENSORS_CONFIG_FILE", str(config_path))

    assert manager._load_config() == expected


def test_default_jeti_baudrate_uses_specbos_defaults() -> None:
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2"}) == 115200
    assert manager._default_jeti_baudrate({"label": "Jeti Spectraval 1511"}) == 921600
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2", "baudrate": 230400}) == 230400


def test_legacy_data_prefix_resolves_inside_selected_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(manager, "DATA_DIR", str(tmp_path))

    assert manager._resolve_data_path("data/live.cap") == str(
        (tmp_path / "live.cap").resolve()
    )


def test_sensor_health_reports_and_clears_polling_errors() -> None:
    manager._set_sensor_error("EKO-00", "connection refused")
    try:
        assert manager.get_sensor_health() == (
            "degraded",
            ["EKO-00: connection refused"],
        )
    finally:
        manager._clear_sensor_error("EKO-00")

    assert manager.get_sensor_health() == ("healthy", [])


@dataclass
class FakeClient:
    id: str
    source: str

    def poll(self):
        if self.source == "physical":
            return []
        return [SensorReading(sensor_id=f"{self.id}-SIM", metric="simulated", value=1.0, ts=1.0)]


def _sensor_config() -> dict:
    return {
        "t10a": [
            {
                "device_id": "KM1",
                "port": "COM3",
                "interval_s": 60,
                "heads": [{"head_no": 0, "sensor_id": "T10A1-H1", "label": "T10A"}],
            }
        ],
        "jeti_spectraval": [
            {
                "sensor_id": "JETI-00",
                "device_id": "JETI",
                "transport": "file",
                "template_path": "jeti_template.cap",
                "output_path": "data/live.cap",
                "interval_s": 5,
            }
        ],
        "eko_ms90_plus": [
            {
                "sensor_id": "EKO-00",
                "device_id": "EKO-CBOX-01",
                "host": "192.168.2.20",
                "port": 502,
                "slave_address": 1,
                "timeout_s": 3.0,
                "float_byte_order": "ABCD",
            }
        ],
    }


def _disable_sensor_db(monkeypatch) -> None:
    monkeypatch.setattr(manager, "register_sensor", lambda **kwargs: None)
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: None)
    monkeypatch.setattr(
        manager,
        "resolve_serial_port",
        lambda config: SerialPortInfo(device=str(config["port"])),
    )


def test_production_creates_eko_tcp_client_without_com_port(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    captured = {}
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "_load_config", lambda: {"eko_ms90_plus": _sensor_config()["eko_ms90_plus"]})

    def fake_eko_client(**kwargs):
        captured.update(kwargs)
        return FakeClient(kwargs["device_id"], "physical")

    monkeypatch.setattr(manager, "EkoCBoxModbusTcpClient", fake_eko_client)

    clients = manager._make_clients_from_config()

    assert len(clients) == 1
    assert captured["host"] == "192.168.2.20"
    assert captured["port"] == 502
    assert "baudrate" not in captured


def test_production_rejects_missing_eko_host(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "eko_ms90_plus": [
                {"sensor_id": "EKO-00", "device_id": "EKO-CBOX-01", "port": 502}
            ]
        },
    )

    with pytest.raises(manager.SensorConfigurationError, match="requires host"):
        manager._make_clients_from_config()


def test_production_rejects_invalid_eko_tcp_port(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "eko_ms90_plus": [
                {
                    "sensor_id": "EKO-00",
                    "device_id": "EKO-CBOX-01",
                    "host": "192.168.2.20",
                    "port": "COM5",
                }
            ]
        },
    )

    with pytest.raises(manager.SensorConfigurationError, match="invalid port"):
        manager._make_clients_from_config()


def test_production_does_not_create_simulated_clients(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(manager, "T10AClient", lambda **kwargs: FakeClient(kwargs["device_id"], "physical"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    monkeypatch.setattr(
        manager,
        "T10ASimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("T10A simulator created in production")),
    )
    monkeypatch.setattr(
        manager,
        "JetiSpectravalSimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("JETI simulator created in production")),
    )
    monkeypatch.setattr(
        manager,
        "EkoMs90PlusSimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EKO simulator created in production")),
    )

    clients = manager._make_clients_from_config()

    assert len(clients) == 3
    assert all(client.source == "physical" for client, _ in clients)


def test_production_does_not_emit_simulated_sensor_readings(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(manager, "T10AClient", lambda **kwargs: FakeClient(kwargs["device_id"], "physical"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )

    clients = manager._make_clients_from_config()
    readings = [r for client, _ in clients for r in client.poll()]

    assert readings == []


def test_external_acquisition_registers_sensors_without_opening_hardware(
    monkeypatch,
) -> None:
    registered = []
    pruned = []
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(
        manager,
        "SENSOR_ACQUISITION",
        SensorAcquisition.EXTERNAL,
    )
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(
        manager,
        "register_sensor",
        lambda **kwargs: registered.append(kwargs["sensor_id"]),
    )
    monkeypatch.setattr(
        manager,
        "prune_sensors_to_ids",
        lambda sensor_ids: pruned.extend(sensor_ids),
    )
    monkeypatch.setattr(
        manager,
        "resolve_serial_port",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("API container attempted serial discovery")
        ),
    )
    monkeypatch.setattr(
        manager,
        "T10AClient",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("API container opened T-10A")
        ),
    )
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("API container opened JETI")
        ),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("API container opened EKO")
        ),
    )

    clients = manager._make_clients_from_config()

    assert clients == []
    assert set(registered) == {"T10A1-H1", "JETI-00", "EKO-00"}
    assert set(pruned) == {"T10A1-H1", "JETI-00", "EKO-00"}


def test_embedded_mode_hands_external_devices_to_the_agent(monkeypatch) -> None:
    registered = {}
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "SENSOR_INGEST_TOKEN", "test-token")
    monkeypatch.setattr(manager, "SENSOR_ACQUISITION", SensorAcquisition.EMBEDDED)
    config = _sensor_config()
    config["t10a"][0]["acquisition"] = "external"
    config["jeti_spectraval"] = []
    monkeypatch.setattr(manager, "_load_config", lambda: config)
    monkeypatch.setattr(
        manager,
        "register_sensor",
        lambda **kwargs: registered.__setitem__(kwargs["sensor_id"], kwargs["config"]),
    )
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: None)
    monkeypatch.setattr(
        manager,
        "resolve_serial_port",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("API container attempted serial discovery")
        ),
    )
    monkeypatch.setattr(
        manager,
        "T10AClient",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("API container opened T-10A")
        ),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )

    clients = manager._make_clients_from_config()

    assert [client.id for client, _interval in clients] == ["EKO-CBOX-01"]
    assert registered["T10A1-H1"]["acquisition"] == "external"
    assert registered["EKO-00"]["acquisition"] == "embedded"


def test_invalid_device_acquisition_is_rejected(monkeypatch) -> None:
    config = _sensor_config()
    config["eko_ms90_plus"][0]["acquisition"] = "agent"
    monkeypatch.setattr(manager, "_load_config", lambda: config)

    with pytest.raises(manager.SensorConfigurationError, match="acquisition"):
        manager.validate_sensor_configuration()


def test_enabled_external_device_requires_ingest_token(monkeypatch) -> None:
    monkeypatch.setattr(manager, "SENSOR_ACQUISITION", SensorAcquisition.EMBEDDED)
    monkeypatch.setattr(manager, "SENSOR_INGEST_TOKEN", "")
    config = _sensor_config()
    config["t10a"][0]["acquisition"] = "external"
    monkeypatch.setattr(manager, "_load_config", lambda: config)

    with pytest.raises(manager.SensorConfigurationError, match="SVC_SENSOR_INGEST_TOKEN"):
        manager.validate_sensor_configuration()

    config["t10a"][0]["enabled"] = False
    manager.validate_sensor_configuration()


def test_embedded_health_checks_staleness_only_for_external_devices(
    monkeypatch,
) -> None:
    monkeypatch.setattr(manager, "SENSOR_ACQUISITION", SensorAcquisition.EMBEDDED)
    monkeypatch.setattr(
        manager,
        "fetch_sensor_ingest_status",
        lambda: [
            {"sensor_id": "T10A1-H1", "received_ts": None, "acquisition": "external"},
            {"sensor_id": "EKO-00", "received_ts": None, "acquisition": "embedded"},
        ],
    )

    assert manager.get_sensor_health() == (
        "degraded",
        ["T10A1-H1: no observation received from the external Sensor Agent"],
    )


def test_production_aligns_active_sensors_without_deleting_history(monkeypatch) -> None:
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "_load_config", lambda: {"eko_ms90_plus": _sensor_config()["eko_ms90_plus"]})
    monkeypatch.setattr(manager, "register_sensor", lambda **kwargs: None)
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    pruned = []
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: pruned.extend(sensor_ids))

    manager._make_clients_from_config()

    assert pruned == ["EKO-00"]


def test_development_uses_simulated_sensors(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.DEVELOPMENT)
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(
        manager,
        "T10AClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("T10A physical client created in development")),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EKO physical client created in development")),
    )
    monkeypatch.setattr(manager, "T10ASimClient", lambda **kwargs: FakeClient(kwargs["device_id"], "simulated"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    monkeypatch.setattr(
        manager,
        "JetiSpectravalSimClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "simulated"),
    )
    monkeypatch.setattr(
        manager,
        "EkoMs90PlusSimClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "simulated"),
    )

    clients = manager._make_clients_from_config()
    simulated_sources = [client.source for client, _ in clients]

    assert simulated_sources.count("simulated") == 3


def test_development_rejects_invalid_eko_port(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.DEVELOPMENT)
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "eko_ms90_plus": [
                {
                    "sensor_id": "EKO-00",
                    "device_id": "EKO-CBOX-01",
                    "port": "COM5",
                    "slave_address": 1,
                    "float_byte_order": "ABCD",
                }
            ]
        },
    )
    with pytest.raises(manager.SensorConfigurationError, match="invalid port"):
        manager._make_clients_from_config()


def test_disabled_sensor_config_is_not_validated_or_registered(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "t10a": [{"enabled": False, "device_id": "retired"}],
            "jeti_spectraval": [{"enabled": False, "sensor_id": "retired"}],
            "eko_ms90_plus": [{"enabled": False, "sensor_id": "retired"}],
        },
    )

    assert manager._make_clients_from_config() == []


class AcknowledgingClient:
    id = "JETI-SB-1"

    def __init__(self) -> None:
        self.acknowledged = 0
        self.rejected = 0

    def poll(self):
        return [
            SensorReading(
                sensor_id="SPECBOS-1",
                metric="spectrum",
                value=0.0,
                ts=100.0,
                spectrum=[1.0, 2.0],
            ),
            SensorReading(
                sensor_id="SPECBOS-1",
                metric="lux",
                value=42.0,
                ts=100.0,
            ),
        ]

    def acknowledge(self) -> None:
        self.acknowledged += 1

    def reject(self) -> None:
        self.rejected += 1


def test_embedded_poll_is_batched_before_source_cursor_is_acknowledged(
    monkeypatch,
) -> None:
    client = AcknowledgingClient()
    stored = []
    monkeypatch.setattr(
        manager,
        "ingest_sensor_events",
        lambda events: stored.extend(events) or (len(events), 0),
    )

    readings = manager._poll_and_persist(client)

    assert len(readings) == 2
    assert len(stored) == 1
    assert stored[0].sensor_id == "SPECBOS-1"
    assert stored[0].metrics == {"lux": 42.0}
    assert stored[0].spectrum == [1.0, 2.0]
    assert client.acknowledged == 1
    assert client.rejected == 0


def test_embedded_poll_rejects_source_batch_when_database_write_fails(
    monkeypatch,
) -> None:
    client = AcknowledgingClient()

    def fail(_events):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(manager, "ingest_sensor_events", fail)

    with pytest.raises(RuntimeError, match="database unavailable"):
        manager._poll_and_persist(client)

    assert client.acknowledged == 0
    assert client.rejected == 1
