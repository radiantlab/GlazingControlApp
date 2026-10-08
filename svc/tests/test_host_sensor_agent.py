from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import pytest

from app.sensors.host_agent import (
    ClientConstructors,
    ClientSpec,
    HostAgentConfigurationError,
    OutboxSender,
    SQLiteOutbox,
    SensorWorker,
    build_client_specs,
    readings_to_events,
)
from app.sensors.interface import SensorReading
from app.sensors.serial_discovery import SerialPortInfo


class FakeClient:
    def __init__(self, *, readings=(), last_error=None, **kwargs):
        self.id = str(kwargs.get("device_id", "fake"))
        self.kwargs = kwargs
        self.readings = list(readings)
        self.last_error = last_error
        self.closed = False

    def poll(self):
        return list(self.readings)

    def close(self):
        self.closed = True


def test_build_specs_resolves_current_com_port_on_every_reconnect(tmp_path):
    ports = iter(("COM4", "COM9"))
    constructed = []

    def resolve(_selector):
        return SerialPortInfo(device=next(ports), serial_number="stable-device")

    def t10a(**kwargs):
        constructed.append(kwargs)
        return FakeClient(**kwargs)

    config = {
        "t10a": [
            {
                "device_id": "KM1",
                "port": "AUTO",
                "port_identity": {"serial_number": "stable-device"},
                "heads": [{"head_no": 0, "sensor_id": "T10A1-H1"}],
            }
        ],
        "jeti_spectraval": [],
        "eko_ms90_plus": [],
    }
    specs = build_client_specs(
        config,
        data_dir=tmp_path,
        resolver=resolve,
        constructors=ClientConstructors(t10a=t10a),
    )

    first = specs[0].factory()
    second = specs[0].factory()

    assert constructed[0]["port"] == "COM4"
    assert constructed[1]["port"] == "COM9"
    assert first.host_agent_source == "t10a:KM1:COM4"
    assert second.host_agent_source == "t10a:KM1:COM9"


def test_build_specs_covers_jeti_serial_file_and_eko(tmp_path):
    calls = []

    def constructor(kind):
        def create(**kwargs):
            calls.append((kind, kwargs))
            return FakeClient(**kwargs)

        return create

    config = {
        "t10a": [],
        "jeti_spectraval": [
            {
                "sensor_id": "JETI-1",
                "device_id": "SV-1",
                "transport": "serial_scpi",
                "port": "COM7",
            },
            {
                "sensor_id": "JETI-2",
                "device_id": "SV-2",
                "transport": "file",
                "output_path": "data/jeti/live.cap",
            },
        ],
        "eko_ms90_plus": [
            {
                "sensor_id": "EKO-1",
                "device_id": "CBOX-1",
                "host": "192.0.2.10",
            }
        ],
    }
    constructors = ClientConstructors(
        jeti_serial=constructor("serial"),
        jeti_file=constructor("file"),
        eko=constructor("eko"),
    )
    specs = build_client_specs(
        config,
        data_dir=tmp_path,
        resolver=lambda _selector: SerialPortInfo(device="COM7"),
        constructors=constructors,
    )

    clients = [spec.factory() for spec in specs]

    assert [spec.name for spec in specs] == ["jeti:SV-1", "jeti:SV-2", "eko:CBOX-1"]
    assert calls[0][1]["port"] == "COM7"
    assert calls[1][1]["input_path"] == str((tmp_path / "jeti/live.cap").resolve())
    assert calls[2][1]["host"] == "192.0.2.10"
    assert all(client.host_agent_source for client in clients)


def test_build_specs_takes_only_devices_marked_external(tmp_path):
    # Mirrors the production template: the API container reads the LiVal
    # capture (input_path, which the agent cannot read) and the C-BOX itself,
    # and hands only the COM-port T-10A to the agent.
    config = {
        "t10a": [
            {
                "device_id": "KM1",
                "port": "AUTO",
                "port_identity": {"serial_number": "stable-device"},
                "acquisition": "external",
                "heads": [{"head_no": 0, "sensor_id": "T10A1-H1"}],
            }
        ],
        "jeti_spectraval": [
            {
                "sensor_id": "SPECBOS-1",
                "device_id": "JETI-SB-1",
                "transport": "file",
                "input_path": "specbos-lival.capture",
            }
        ],
        "eko_ms90_plus": [
            {"sensor_id": "EKO-00", "device_id": "CBOX-1", "host": "192.0.2.10"}
        ],
    }

    specs = build_client_specs(
        config,
        data_dir=tmp_path,
        resolver=lambda _selector: SerialPortInfo(device="COM4"),
        constructors=ClientConstructors(t10a=lambda **kwargs: FakeClient(**kwargs)),
    )

    assert [spec.name for spec in specs] == ["t10a:KM1"]


def test_build_specs_reads_explicit_lival_capture_path_from_environment(tmp_path):
    calls = []
    capture_file = tmp_path / "Desktop" / "JETI_capture.xlsx"
    capture_file.parent.mkdir()
    capture_file.write_text("Date and Time:; ", encoding="utf-8")
    data_dir = tmp_path / "data"

    def jeti_file(**kwargs):
        calls.append(kwargs)
        return FakeClient(**kwargs)

    config = {
        "t10a": [],
        "jeti_spectraval": [
            {
                "sensor_id": "SPECBOS-1",
                "device_id": "JETI-SB-1",
                "transport": "file",
                "output_path": "jeti_capture",
                "capture_path_env": "SVC_JETI_CAPTURE_PATH",
            }
        ],
        "eko_ms90_plus": [],
    }

    specs = build_client_specs(
        config,
        data_dir=data_dir,
        environment={"SVC_JETI_CAPTURE_PATH": str(capture_file)},
        constructors=ClientConstructors(jeti_file=jeti_file),
    )
    client = specs[0].factory()

    assert calls[0]["input_path"] == str(capture_file.resolve())
    assert calls[0]["input_kind"] == "file"
    assert calls[0]["cursor_dir"] == str(
        (data_dir / ".sensor-agent-cursors").resolve()
    )
    assert client.host_agent_source == f"jeti-file:{capture_file.resolve()}"


def test_build_specs_requires_configured_lival_capture_environment(tmp_path):
    config = {
        "t10a": [],
        "jeti_spectraval": [
            {
                "sensor_id": "SPECBOS-1",
                "transport": "file",
                "output_path": "jeti_capture",
                "capture_path_env": "SVC_JETI_CAPTURE_PATH",
            }
        ],
        "eko_ms90_plus": [],
    }

    with pytest.raises(
        HostAgentConfigurationError,
        match="requires environment variable SVC_JETI_CAPTURE_PATH",
    ):
        build_client_specs(config, data_dir=tmp_path, environment={})


def test_readings_become_one_retry_stable_event_per_observation():
    readings = [
        SensorReading("JETI-1", "spectrum", 0.0, 1000.25, [1.0, 2.0]),
        SensorReading("JETI-1", "lux", 42.5, 1000.25),
        SensorReading("JETI-1", "cct_ohno_k", 5000.0, 1000.25),
    ]

    first = readings_to_events(
        readings,
        agent_id="trailer-pc",
        source="jeti-serial:COM7",
    )
    retry = readings_to_events(
        readings,
        agent_id="trailer-pc",
        source="jeti-serial:COM7",
    )

    assert first == retry
    assert len(first) == 1
    assert first[0]["metrics"] == {"lux": 42.5, "cct_ohno_k": 5000.0}
    assert first[0]["spectrum"] == [1.0, 2.0]
    assert first[0]["event_id"].startswith("trailer-pc:")


class FakeResponse:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self.payload = payload

    def json(self):
        return self.payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, *, data, headers, timeout):
        self.calls.append((url, data, dict(headers), timeout))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_outbox_persists_exact_json_and_sender_acknowledges(tmp_path):
    outbox = SQLiteOutbox(tmp_path / "outbox.db", clock=lambda: 100.0)
    event = {
        "event_id": "agent:event-1",
        "sensor_id": "T10A1-H1",
        "observed_ts": 1234.5,
        "metrics": {"lux": 100.0},
        "source": "windows-host:test:COM4",
    }
    assert outbox.enqueue([event]) == (1, 0)
    persisted = outbox.payloads()[0]
    transport = FakeTransport(
        [FakeResponse(200, payload={"accepted": 1, "duplicates": 0})]
    )
    sender = OutboxSender(
        outbox=outbox,
        endpoint="http://127.0.0.1:8000/sensors/ingest",
        token="secret",
        transport=transport,
    )

    result = sender.deliver_once()

    assert result.delivered == 1
    assert outbox.count() == 0
    _, body, headers, _ = transport.calls[0]
    assert body == ('{"events":[' + persisted + "]}").encode()
    assert headers["X-Sensor-Ingest-Token"] == "secret"


def test_failed_delivery_remains_durable_and_retries_same_event(tmp_path):
    now = [100.0]
    outbox = SQLiteOutbox(tmp_path / "outbox.db", clock=lambda: now[0])
    event = {
        "event_id": "agent:event-1",
        "sensor_id": "EKO-1",
        "observed_ts": 1234.5,
        "metrics": {"ghi_w_m2": 500.0},
    }
    outbox.enqueue([event])
    transport = FakeTransport(
        [
            RuntimeError("offline"),
            FakeResponse(200, payload={"accepted": 1, "duplicates": 0}),
        ]
    )
    sender = OutboxSender(
        outbox=outbox,
        endpoint="http://127.0.0.1:8000/sensors/ingest",
        token="secret",
        transport=transport,
        retry_base_s=1.0,
    )

    failed = sender.deliver_once()
    assert failed.delivered == 0
    assert outbox.count() == 1
    assert sender.deliver_once().attempted == 0

    now[0] += 1.0
    delivered = sender.deliver_once()

    assert delivered.delivered == 1
    assert transport.calls[0][1] == transport.calls[1][1]
    assert outbox.count() == 0


def test_worker_retries_factory_after_hotplug_failure(tmp_path):
    outbox = SQLiteOutbox(tmp_path / "outbox.db")
    attempts = []
    stop_event = threading.Event()

    def factory():
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise OSError("device absent")
        return FakeClient(
            device_id="KM1",
            readings=[SensorReading("T10A1-H1", "lux", 123.0, time.time())],
        )

    spec = ClientSpec(
        name="t10a:KM1",
        interval_s=60.0,
        factory=factory,
        empty_is_error=True,
    )
    worker = SensorWorker(
        spec=spec,
        outbox=outbox,
        agent_id="test-host",
        reconnect_initial_s=0.01,
        reconnect_max_s=0.02,
    )
    thread = threading.Thread(target=worker.run, args=(stop_event,))
    thread.start()
    deadline = time.monotonic() + 2.0
    while outbox.count() == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    stop_event.set()
    worker.close()
    thread.join(timeout=1.0)

    assert len(attempts) >= 2
    assert outbox.count() == 1
    assert not thread.is_alive()
