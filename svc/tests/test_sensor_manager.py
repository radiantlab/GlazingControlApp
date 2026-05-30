from __future__ import annotations

import json
from dataclasses import dataclass

from app.sensors import manager
from app.sensors import serial_autodetect
from app.sensors.interface import SensorReading


def test_load_config_resolves_repo_relative_env_path(tmp_path, monkeypatch) -> None:
    repo_dir = tmp_path / "repo"
    svc_dir = repo_dir / "svc"
    data_dir = svc_dir / "data"
    data_dir.mkdir(parents=True)

    config_path = data_dir / "sensors_config.json"
    expected = {"t10a": [], "jeti_spectraval": [], "eko_ms90_plus": []}
    config_path.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.chdir(svc_dir)
    monkeypatch.setattr(manager, "_SVC_DIR", str(svc_dir))
    monkeypatch.setattr(manager, "_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("SENSORS_CONFIG_FILE", "svc/data/sensors_config.json")

    assert manager._load_config() == expected


def test_default_jeti_baudrate_uses_specbos_defaults() -> None:
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2"}) == 115200
    assert manager._default_jeti_baudrate({"label": "Jeti Spectraval 1511"}) == 921600
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2", "baudrate": 230400}) == 230400
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2", "baudrate": "auto"}) == 115200


@dataclass
class FakeClient:
    id: str
    source: str

    def poll(self):
        if self.source == "real":
            return []
        return [SensorReading(sensor_id=f"{self.id}-SIM", metric="simulated", value=1.0, ts=1.0)]


@dataclass
class FakePortInfo:
    device: str
    name: str = ""
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    location: str = ""
    vid: int | None = None
    pid: int | None = None


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


def test_manager_creates_eko_tcp_client_without_com_port(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    captured = {}
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(manager, "_load_config", lambda: {"eko_ms90_plus": _sensor_config()["eko_ms90_plus"]})

    def fake_eko_client(**kwargs):
        captured.update(kwargs)
        return FakeClient(kwargs["device_id"], "real")

    monkeypatch.setattr(manager, "EkoCBoxModbusTcpClient", fake_eko_client)

    clients = manager._make_clients_from_config()

    assert len(clients) == 1
    assert captured["host"] == "192.168.2.20"
    assert captured["port"] == 502
    assert "baudrate" not in captured


def test_manager_logs_missing_eko_host_in_real_mode(monkeypatch, caplog) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "eko_ms90_plus": [
                {"sensor_id": "EKO-00", "device_id": "EKO-CBOX-01", "port": 502}
            ]
        },
    )

    with caplog.at_level("WARNING"):
        clients = manager._make_clients_from_config()

    assert clients == []
    assert "missing 'host'" in caplog.text


def test_manager_logs_invalid_eko_tcp_port_in_real_mode(monkeypatch, caplog) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "real")
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

    with caplog.at_level("WARNING"):
        clients = manager._make_clients_from_config()

    assert clients == []
    assert "invalid Modbus TCP config" in caplog.text
    assert "COM5" in caplog.text


def test_real_mode_does_not_create_sim_clients(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(manager, "T10AClient", lambda **kwargs: FakeClient(kwargs["device_id"], "real"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )
    monkeypatch.setattr(
        manager,
        "T10ASimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("T10A sim created in real mode")),
    )
    monkeypatch.setattr(
        manager,
        "JetiSpectravalSimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("JETI sim created in real mode")),
    )
    monkeypatch.setattr(
        manager,
        "EkoMs90PlusSimClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EKO sim created in real mode")),
    )

    clients = manager._make_clients_from_config()

    assert len(clients) == 3
    assert all(client.source == "real" for client, _ in clients)


def test_real_mode_does_not_emit_simulated_sensor_readings(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(manager, "T10AClient", lambda **kwargs: FakeClient(kwargs["device_id"], "real"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )

    clients = manager._make_clients_from_config()
    readings = [r for client, _ in clients for r in client.poll()]

    assert readings == []


def test_real_mode_autodetects_serial_ports_and_reserves_them(monkeypatch) -> None:
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(
        manager,
        "_load_config",
        lambda: {
            "t10a": [
                {
                    "device_id": "KM1",
                    "port": "auto",
                    "heads": [{"head_no": 0, "sensor_id": "T10A1-H1", "label": "T10A"}],
                }
            ],
            "jeti_spectraval": [
                {
                    "sensor_id": "JETI-00",
                    "device_id": "JETI",
                    "transport": "serial_scpi",
                    "port": "auto",
                    "baudrate_candidates": [115200, 921600],
                }
            ],
            "eko_ms90_plus": [],
        },
    )
    monkeypatch.setattr(
        serial_autodetect.list_ports,
        "comports",
        lambda: [FakePortInfo("COM3"), FakePortInfo("COM4")],
    )

    registered = {}
    monkeypatch.setattr(manager, "register_sensor", lambda **kwargs: registered.setdefault(kwargs["sensor_id"], kwargs))
    monkeypatch.setattr(manager, "delete_sensor_readings_for_ids", lambda sensor_ids: None)
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: None)

    class FakeT10AClient:
        @staticmethod
        def probe_port(**kwargs):
            return kwargs["port"] == "COM3"

        def __init__(self, **kwargs):
            self.source = "real"
            self.kwargs = kwargs

        def poll(self):
            return []

    class FakeJetiClient:
        @staticmethod
        def probe_port(**kwargs):
            return kwargs["port"] == "COM4" and kwargs["baudrate"] == 921600

        def __init__(self, **kwargs):
            self.source = "real"
            self.kwargs = kwargs

        def poll(self):
            return []

    monkeypatch.setattr(manager, "T10AClient", FakeT10AClient)
    monkeypatch.setattr(manager, "JetiSpecfirmClient", FakeJetiClient)

    clients = manager._make_clients_from_config()

    assert len(clients) == 2
    t10a_client = clients[0][0]
    jeti_client = clients[1][0]
    assert t10a_client.kwargs["port"] == "COM3"
    assert jeti_client.kwargs["port"] == "COM4"
    assert jeti_client.kwargs["baudrate"] == 921600
    assert registered["T10A1-H1"]["config"]["port"] == "COM3"
    assert registered["JETI-00"]["config"]["port"] == "COM4"


def test_real_mode_clears_stale_readings_for_configured_sensors(monkeypatch) -> None:
    monkeypatch.setattr(manager, "MODE", "real")
    monkeypatch.setattr(manager, "_load_config", lambda: {"eko_ms90_plus": _sensor_config()["eko_ms90_plus"]})
    monkeypatch.setattr(manager, "register_sensor", lambda **kwargs: None)
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )
    cleared = []
    pruned = []
    monkeypatch.setattr(manager, "delete_sensor_readings_for_ids", lambda sensor_ids: cleared.extend(sensor_ids))
    monkeypatch.setattr(manager, "prune_sensors_to_ids", lambda sensor_ids: pruned.extend(sensor_ids))

    manager._make_clients_from_config()

    assert cleared == ["EKO-00"]
    assert pruned == ["EKO-00"]


def test_sim_mode_uses_simulated_sensors(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "sim")
    monkeypatch.setattr(manager, "_load_config", _sensor_config)
    monkeypatch.setattr(
        manager,
        "T10AClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("T10A real created in sim mode")),
    )
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EKO real created in sim mode")),
    )
    monkeypatch.setattr(manager, "T10ASimClient", lambda **kwargs: FakeClient(kwargs["device_id"], "sim"))
    monkeypatch.setattr(
        manager,
        "JetiSpectravalFileWatcher",
        lambda **kwargs: FakeClient(kwargs["device_id"], "real"),
    )
    monkeypatch.setattr(
        manager,
        "JetiSpectravalSimClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "sim"),
    )
    monkeypatch.setattr(
        manager,
        "EkoMs90PlusSimClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "sim"),
    )

    clients = manager._make_clients_from_config()
    sim_sources = [client.source for client, _ in clients]

    assert sim_sources.count("sim") == 3


def test_sim_mode_tolerates_legacy_eko_com_port_config(monkeypatch) -> None:
    _disable_sensor_db(monkeypatch)
    monkeypatch.setattr(manager, "MODE", "sim")
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
    monkeypatch.setattr(
        manager,
        "EkoCBoxModbusTcpClient",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("EKO real created in sim mode")),
    )
    monkeypatch.setattr(
        manager,
        "EkoMs90PlusSimClient",
        lambda **kwargs: FakeClient(kwargs["device_id"], "sim"),
    )

    clients = manager._make_clients_from_config()

    assert len(clients) == 1
    assert clients[0][0].source == "sim"
