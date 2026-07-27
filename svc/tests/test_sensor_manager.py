from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from app.config import Environment
from app.sensors import manager
from app.sensors.interface import SensorReading


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
    monkeypatch.setattr(manager, "delete_sensor_readings_for_ids", lambda sensor_ids: None)
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: None)


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


def test_production_clears_stale_readings_for_configured_sensors(monkeypatch) -> None:
    monkeypatch.setattr(manager, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(manager, "_load_config", lambda: {"eko_ms90_plus": _sensor_config()["eko_ms90_plus"]})
    monkeypatch.setattr(manager, "register_sensor", lambda **kwargs: None)
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "physical"),
    )
    cleared = []
    pruned = []
    monkeypatch.setattr(manager, "delete_sensor_readings_for_ids", lambda sensor_ids: cleared.extend(sensor_ids))
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: pruned.extend(sensor_ids))

    manager._make_clients_from_config()

    assert cleared == ["EKO-00"]
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
