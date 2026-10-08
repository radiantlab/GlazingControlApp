"""Native-host physical sensor collection with durable API delivery.

The production web service can run inside a Linux Podman VM, but Windows COM
ports cannot be opened reliably from that VM.  This module keeps physical I/O
on the Windows host and forwards idempotent observations to the service.

It intentionally never imports :mod:`app.state` and never opens ``audit.db``.
The only local database it owns is a durable delivery outbox.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from .eko_cbox_modbus_tcp_client import EkoCBoxModbusTcpClient
from .interface import SensorClient, SensorReading
from .jeti_specfirm_client import JetiSpecfirmClient
from .jeti_spectraval_watcher import JetiSpectravalFileWatcher
from .serial_discovery import (
    SerialPortInfo,
    SerialPortSelector,
    enumerate_serial_ports,
    resolve_serial_port,
)
from .t10a_client import T10AClient, T10AHeadConfig


logger = logging.getLogger(__name__)


class HostAgentConfigurationError(ValueError):
    """Raised when host-agent configuration is incomplete or unsafe."""


class SensorPollError(RuntimeError):
    """Raised when a client reports a failed or empty physical poll."""


class HttpResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> HttpResponse: ...


ClientFactory = Callable[[], SensorClient]
SerialResolver = Callable[[SerialPortSelector], SerialPortInfo]


@dataclass(frozen=True, slots=True)
class ClientConstructors:
    """Injectable constructors keep hardware-free tests straightforward."""

    t10a: Callable[..., SensorClient] = T10AClient
    jeti_serial: Callable[..., SensorClient] = JetiSpecfirmClient
    jeti_file: Callable[..., SensorClient] = JetiSpectravalFileWatcher
    eko: Callable[..., SensorClient] = EkoCBoxModbusTcpClient


@dataclass(frozen=True, slots=True)
class ClientSpec:
    name: str
    interval_s: float
    factory: ClientFactory
    empty_is_error: bool
    spectrum_wavelength_start: int = 380
    spectrum_wavelength_step: int = 1


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: str
    payload_json: str
    attempts: int


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    attempted: int
    delivered: int
    status_code: int | None = None
    error: str | None = None


def _diagnostic(level: int, event: str, **fields: Any) -> dict[str, Any]:
    record = {"event": event, **fields}
    logger.log(
        level,
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str),
    )
    return record


def load_sensor_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load an environment-specific ``sensors_config.json``."""
    config_path = Path(path).expanduser().resolve(strict=False)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HostAgentConfigurationError(
            f"Sensor configuration does not exist: {config_path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HostAgentConfigurationError(
            f"Unable to load sensor configuration {config_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise HostAgentConfigurationError("Sensor configuration must be a JSON object")
    for key in ("t10a", "jeti_spectraval", "eko_ms90_plus"):
        value = payload.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise HostAgentConfigurationError(f"{key} must be an array of objects")
    return payload


def _positive_float(value: Any, *, field: str, default: float) -> float:
    try:
        parsed = float(default if value in (None, "") else value)
    except (TypeError, ValueError) as exc:
        raise HostAgentConfigurationError(f"{field} must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise HostAgentConfigurationError(f"{field} must be greater than zero")
    return parsed


def _positive_int(value: Any, *, field: str, default: int) -> int:
    try:
        parsed = int(default if value in (None, "") else value)
    except (TypeError, ValueError) as exc:
        raise HostAgentConfigurationError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise HostAgentConfigurationError(f"{field} must be greater than zero")
    return parsed


def _resolve_data_path(raw_path: str, data_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        if path.parts and path.parts[0].casefold() == "data":
            path = Path(*path.parts[1:])
        path = data_dir / path
    return path.resolve(strict=False)


def _source_for(client: SensorClient, fallback: str) -> str:
    return str(getattr(client, "host_agent_source", fallback))


def _default_jeti_baudrate(config: Mapping[str, Any]) -> int:
    if config.get("baudrate") not in (None, ""):
        return _positive_int(
            config["baudrate"],
            field="jeti_spectraval[].baudrate",
            default=921600,
        )
    fingerprint = " ".join(
        str(config.get(key, ""))
        for key in ("device_id", "sensor_id", "label", "device_model", "model")
    ).casefold()
    return 115200 if "specbos" in fingerprint else 921600


def _serial_factory(
    *,
    selector: SerialPortSelector,
    resolver: SerialResolver,
    constructor: Callable[..., SensorClient],
    constructor_kwargs: Mapping[str, Any],
    source_prefix: str,
) -> ClientFactory:
    """Resolve the current COM name on every construction/reconnect."""

    def create() -> SensorClient:
        port = resolver(selector)
        client = constructor(port=port.device, **dict(constructor_kwargs))
        setattr(client, "host_agent_source", f"{source_prefix}:{port.device}")
        return client

    return create


def build_client_specs(
    config: Mapping[str, Any],
    *,
    data_dir: str | os.PathLike[str],
    environment: Mapping[str, str] | None = None,
    resolver: SerialResolver = resolve_serial_port,
    constructors: ClientConstructors | None = None,
) -> list[ClientSpec]:
    """Build lazy physical-client factories from sensor configuration.

    Serial resolution happens inside each factory so a reconnect also performs
    a fresh Windows port inventory and follows a stable USB identity to its new
    COM name.
    """
    constructors = constructors or ClientConstructors()
    selected_environment = os.environ if environment is None else environment
    selected_data_dir = Path(data_dir).expanduser().resolve(strict=False)
    specs: list[ClientSpec] = []
    names: set[str] = set()

    def add(spec: ClientSpec) -> None:
        if spec.name in names:
            raise HostAgentConfigurationError(
                f"Duplicate physical device identifier: {spec.name}"
            )
        names.add(spec.name)
        specs.append(spec)

    for index, item in enumerate(config.get("t10a", [])):
        if item.get("enabled", True) is False:
            continue
        device_id = str(item.get("device_id") or "").strip()
        if not device_id:
            raise HostAgentConfigurationError(f"t10a[{index}] requires device_id")
        raw_heads = item.get("heads")
        if not isinstance(raw_heads, list) or not raw_heads:
            raise HostAgentConfigurationError(
                f"t10a[{index}] requires at least one head"
            )
        heads: list[T10AHeadConfig] = []
        for head_index, raw_head in enumerate(raw_heads):
            if not isinstance(raw_head, dict) or not raw_head.get("sensor_id"):
                raise HostAgentConfigurationError(
                    f"t10a[{index}].heads[{head_index}] is invalid"
                )
            try:
                head_no = int(raw_head["head_no"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HostAgentConfigurationError(
                    f"t10a[{index}].heads[{head_index}].head_no must be an integer"
                ) from exc
            heads.append(
                T10AHeadConfig(
                    head_no=head_no,
                    sensor_id=str(raw_head["sensor_id"]),
                    label=str(raw_head.get("label") or raw_head["sensor_id"]),
                    location=raw_head.get("location"),
                )
            )

        selector = SerialPortSelector.from_config(item)
        interval_s = _positive_float(
            item.get("interval_s"),
            field=f"t10a[{index}].interval_s",
            default=60.0,
        )
        factory = _serial_factory(
            selector=selector,
            resolver=resolver,
            constructor=constructors.t10a,
            source_prefix=f"t10a:{device_id}",
            constructor_kwargs={
                "device_id": device_id,
                "heads": heads,
                "timeout_s": _positive_float(
                    item.get("timeout_s"),
                    field=f"t10a[{index}].timeout_s",
                    default=1.0,
                ),
                "protocol": item.get("protocol", {}),
                "baudrate": _positive_int(
                    item.get("baudrate"),
                    field=f"t10a[{index}].baudrate",
                    default=9600,
                ),
            },
        )
        add(
            ClientSpec(
                name=f"t10a:{device_id}",
                interval_s=interval_s,
                factory=factory,
                empty_is_error=True,
            )
        )

    for index, item in enumerate(config.get("jeti_spectraval", [])):
        if item.get("enabled", True) is False:
            continue
        sensor_id = str(item.get("sensor_id") or f"JETI-{index:02d}")
        device_id = str(item.get("device_id") or sensor_id)
        label = str(item.get("label") or sensor_id)
        location = item.get("location")
        interval_s = _positive_float(
            item.get("interval_s"),
            field=f"jeti_spectraval[{index}].interval_s",
            default=60.0,
        )
        transport = str(item.get("transport", "file")).strip().casefold()
        name = f"jeti:{device_id}"

        if transport in {"serial_scpi", "serial", "specfirm"}:
            selector = SerialPortSelector.from_config(item)
            spectrum_start = _positive_int(
                item.get("wavelength_start_nm"),
                field=f"jeti_spectraval[{index}].wavelength_start_nm",
                default=380,
            )
            spectrum_step = _positive_int(
                item.get("wavelength_step_nm"),
                field=f"jeti_spectraval[{index}].wavelength_step_nm",
                default=1,
            )
            factory = _serial_factory(
                selector=selector,
                resolver=resolver,
                constructor=constructors.jeti_serial,
                source_prefix=f"jeti-serial:{device_id}",
                constructor_kwargs={
                    "device_id": device_id,
                    "sensor_id": sensor_id,
                    "label": label,
                    "location": location,
                    "baudrate": _default_jeti_baudrate(item),
                    "timeout_s": _positive_float(
                        item.get("timeout_s"),
                        field=f"jeti_spectraval[{index}].timeout_s",
                        default=1.0,
                    ),
                    "tint_ms": _positive_float(
                        item.get("tint_ms"),
                        field=f"jeti_spectraval[{index}].tint_ms",
                        default=100.0,
                    ),
                    "avg_count": _positive_int(
                        item.get("avg_count"),
                        field=f"jeti_spectraval[{index}].avg_count",
                        default=1,
                    ),
                    "wavelength_start_nm": spectrum_start,
                    "wavelength_end_nm": _positive_int(
                        item.get("wavelength_end_nm"),
                        field=f"jeti_spectraval[{index}].wavelength_end_nm",
                        default=780,
                    ),
                    "wavelength_step_nm": spectrum_step,
                },
            )
            add(
                ClientSpec(
                    name=name,
                    interval_s=interval_s,
                    factory=factory,
                    empty_is_error=True,
                    spectrum_wavelength_start=spectrum_start,
                    spectrum_wavelength_step=spectrum_step,
                )
            )
            continue

        if transport != "file":
            raise HostAgentConfigurationError(
                f"jeti_spectraval[{index}] has unsupported transport {transport!r}"
            )
        capture_path_env = str(item.get("capture_path_env") or "").strip()
        if capture_path_env:
            raw_output_path = str(
                selected_environment.get(capture_path_env, "")
            ).strip()
            if not raw_output_path:
                raise HostAgentConfigurationError(
                    f"jeti_spectraval[{index}] requires environment variable "
                    f"{capture_path_env}"
                )
        else:
            raw_output_path = str(item.get("output_path") or "").strip()
        if not raw_output_path:
            raise HostAgentConfigurationError(
                f"jeti_spectraval[{index}] file transport requires output_path"
            )
        output_path = _resolve_data_path(raw_output_path, selected_data_dir)
        input_kind = "file" if capture_path_env else str(
            item.get("input_kind") or "auto"
        )
        cursor_dir = (
            selected_data_dir / ".sensor-agent-cursors"
            if capture_path_env
            else None
        )

        def create_file_client(
            *,
            _device_id: str = device_id,
            _sensor_id: str = sensor_id,
            _output_path: Path = output_path,
            _label: str = label,
            _location: Any = location,
            _input_kind: str = input_kind,
            _cursor_dir: Path | None = cursor_dir,
        ) -> SensorClient:
            client = constructors.jeti_file(
                device_id=_device_id,
                sensor_id=_sensor_id,
                input_path=str(_output_path),
                label=_label,
                location=_location,
                svc_root=str(selected_data_dir.parent),
                input_kind=_input_kind,
                cursor_dir=str(_cursor_dir) if _cursor_dir else None,
            )
            setattr(client, "host_agent_source", f"jeti-file:{_output_path}")
            return client

        add(
            ClientSpec(
                name=name,
                interval_s=_positive_float(
                    item.get("watch_interval_s"),
                    field=f"jeti_spectraval[{index}].watch_interval_s",
                    default=1.0,
                ),
                factory=create_file_client,
                empty_is_error=False,
            )
        )

    for index, item in enumerate(config.get("eko_ms90_plus", [])):
        if item.get("enabled", True) is False:
            continue
        sensor_id = str(item.get("sensor_id") or f"EKO-{index:02d}")
        device_id = str(item.get("device_id") or sensor_id)
        host = str(item.get("host") or "").strip()
        if not host:
            raise HostAgentConfigurationError(
                f"eko_ms90_plus[{index}] requires host"
            )
        tcp_port = _positive_int(
            item.get("port"),
            field=f"eko_ms90_plus[{index}].port",
            default=502,
        )
        if tcp_port > 65535:
            raise HostAgentConfigurationError(
                f"eko_ms90_plus[{index}].port must be at most 65535"
            )

        def create_eko_client(
            *,
            _item: Mapping[str, Any] = item,
            _sensor_id: str = sensor_id,
            _device_id: str = device_id,
            _host: str = host,
            _tcp_port: int = tcp_port,
            _index: int = index,
        ) -> SensorClient:
            client = constructors.eko(
                device_id=_device_id,
                sensor_id=_sensor_id,
                host=_host,
                port=_tcp_port,
                slave_address=_positive_int(
                    _item.get("slave_address"),
                    field=f"eko_ms90_plus[{_index}].slave_address",
                    default=1,
                ),
                timeout_s=_positive_float(
                    _item.get("timeout_s"),
                    field=f"eko_ms90_plus[{_index}].timeout_s",
                    default=3.0,
                ),
                label=str(_item.get("label") or _sensor_id),
                location=_item.get("location"),
                float_byte_order=str(_item.get("float_byte_order", "ABCD")),
            )
            setattr(client, "host_agent_source", f"eko-modbus:{_host}:{_tcp_port}")
            return client

        add(
            ClientSpec(
                name=f"eko:{device_id}",
                interval_s=_positive_float(
                    item.get("interval_s"),
                    field=f"eko_ms90_plus[{index}].interval_s",
                    default=5.0,
                ),
                factory=create_eko_client,
                empty_is_error=True,
            )
        )

    return specs


def readings_to_events(
    readings: Iterable[SensorReading],
    *,
    agent_id: str,
    source: str,
    spectrum_wavelength_start: int = 380,
    spectrum_wavelength_step: int = 1,
) -> list[dict[str, Any]]:
    """Combine one poll's scalar and spectral readings into ingest events."""
    grouped: dict[tuple[str, float], dict[str, Any]] = {}
    for reading in readings:
        ts = float(reading.ts)
        value = float(reading.value)
        if not math.isfinite(ts) or ts <= 0 or not math.isfinite(value):
            raise SensorPollError(
                f"Non-finite reading from {source}: {reading.sensor_id}/{reading.metric}"
            )
        key = (str(reading.sensor_id), ts)
        event = grouped.setdefault(
            key,
            {
                "sensor_id": str(reading.sensor_id),
                "observed_ts": ts,
                "metrics": {},
                "source": f"windows-host:{agent_id}:{source}"[:256],
            },
        )
        if reading.metric == "spectrum" and reading.spectrum is not None:
            spectrum = [float(item) for item in reading.spectrum]
            if not spectrum or any(not math.isfinite(item) for item in spectrum):
                raise SensorPollError(
                    f"Invalid spectrum from {source}: {reading.sensor_id}"
                )
            event["spectrum"] = spectrum
            event["spectrum_wavelength_start"] = spectrum_wavelength_start
            event["spectrum_wavelength_step"] = spectrum_wavelength_step
        else:
            event["metrics"][str(reading.metric)] = value

    events: list[dict[str, Any]] = []
    for event in grouped.values():
        # The ingestion contract requires at least one scalar metric. Existing
        # JETI clients emit spectra and their calculated metrics together.
        if not event["metrics"]:
            raise SensorPollError(
                f"Spectrum-only observation is unsupported: {event['sensor_id']}"
            )
        identity_payload = {
            key: value
            for key, value in event.items()
            if key != "event_id"
        }
        identity_json = json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()
        safe_agent_id = "".join(
            char if char.isalnum() or char in "_.:-" else "-"
            for char in agent_id
        )[:48]
        event["event_id"] = f"{safe_agent_id}:{digest}"[:128]
        events.append(event)

    return sorted(
        events,
        key=lambda item: (float(item["observed_ts"]), str(item["sensor_id"])),
    )


class SQLiteOutbox:
    """Thread-safe-by-connection durable storage for exact event JSON."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_ts REAL NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_outbox_due
                ON outbox_events (next_attempt_ts, created_ts)
                """
            )

    def enqueue(self, events: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
        inserted = 0
        now = self._clock()
        with self._connect() as conn:
            for event in events:
                event_id = str(event.get("event_id") or "")
                if not event_id:
                    raise ValueError("Every outbox event requires event_id")
                payload_json = json.dumps(
                    dict(event),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                cursor = conn.execute(
                    """
                    INSERT INTO outbox_events (
                        event_id, payload_json, created_ts, next_attempt_ts
                    ) VALUES (?, ?, ?, 0)
                    ON CONFLICT(event_id) DO NOTHING
                    """,
                    (event_id, payload_json, now),
                )
                inserted += cursor.rowcount
        return inserted, len(events) - inserted

    def due(self, *, limit: int = 250) -> list[OutboxEvent]:
        now = self._clock()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, payload_json, attempts
                FROM outbox_events
                WHERE next_attempt_ts <= ?
                ORDER BY created_ts, event_id
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [OutboxEvent(str(row[0]), str(row[1]), int(row[2])) for row in rows]

    def acknowledge(self, event_ids: Sequence[str]) -> None:
        if not event_ids:
            return
        placeholders = ",".join("?" for _ in event_ids)
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM outbox_events WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            )

    def mark_failed(
        self,
        events: Sequence[OutboxEvent],
        error: str,
        *,
        retry_base_s: float = 1.0,
        retry_max_s: float = 300.0,
    ) -> None:
        if not events:
            return
        now = self._clock()
        with self._connect() as conn:
            for event in events:
                next_attempt = event.attempts + 1
                delay = min(
                    retry_max_s,
                    retry_base_s * (2 ** min(event.attempts, 8)),
                )
                conn.execute(
                    """
                    UPDATE outbox_events
                    SET attempts = ?, next_attempt_ts = ?, last_error = ?
                    WHERE event_id = ?
                    """,
                    (next_attempt, now + delay, error[:2000], event.event_id),
                )

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0])

    def payloads(self) -> list[str]:
        """Return stored JSON for diagnostics and focused tests."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM outbox_events ORDER BY created_ts, event_id"
            ).fetchall()
        return [str(row[0]) for row in rows]


class OutboxSender:
    def __init__(
        self,
        *,
        outbox: SQLiteOutbox,
        endpoint: str,
        token: str,
        transport: HttpTransport | None = None,
        timeout_s: float = 10.0,
        batch_size: int = 250,
        retry_base_s: float = 1.0,
        retry_max_s: float = 300.0,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise HostAgentConfigurationError(
                "Sensor ingestion endpoint must use http:// or https://"
            )
        if not token:
            raise HostAgentConfigurationError(
                "SENSOR_INGEST_TOKEN is required for host-agent delivery"
            )
        self.outbox = outbox
        self.endpoint = endpoint
        self.token = token
        self.transport = transport or requests.Session()
        self.timeout_s = timeout_s
        self.batch_size = batch_size
        self.retry_base_s = retry_base_s
        self.retry_max_s = retry_max_s

    def deliver_once(self) -> DeliveryResult:
        events = self.outbox.due(limit=self.batch_size)
        if not events:
            return DeliveryResult(attempted=0, delivered=0)

        # Embed the persisted JSON verbatim in the batch. A network retry sends
        # byte-for-byte identical event objects with identical event IDs.
        body = (
            '{"events":['
            + ",".join(event.payload_json for event in events)
            + "]}"
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Sensor-Ingest-Token": self.token,
        }
        try:
            response = self.transport.post(
                self.endpoint,
                data=body,
                headers=headers,
                timeout=self.timeout_s,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.outbox.mark_failed(
                events,
                error,
                retry_base_s=self.retry_base_s,
                retry_max_s=self.retry_max_s,
            )
            _diagnostic(
                logging.WARNING,
                "ingest_delivery_failed",
                count=len(events),
                error=error,
            )
            return DeliveryResult(
                attempted=len(events),
                delivered=0,
                error=error,
            )

        if 200 <= int(response.status_code) < 300:
            try:
                result_payload = response.json()
                accounted_for = int(result_payload["accepted"]) + int(
                    result_payload["duplicates"]
                )
                if accounted_for != len(events):
                    raise ValueError(
                        f"server accounted for {accounted_for} of {len(events)} events"
                    )
            except Exception as exc:
                error = f"Invalid success response: {type(exc).__name__}: {exc}"
                self.outbox.mark_failed(
                    events,
                    error,
                    retry_base_s=self.retry_base_s,
                    retry_max_s=self.retry_max_s,
                )
                _diagnostic(
                    logging.WARNING,
                    "ingest_delivery_unconfirmed",
                    count=len(events),
                    status_code=int(response.status_code),
                    error=error,
                )
                return DeliveryResult(
                    attempted=len(events),
                    delivered=0,
                    status_code=int(response.status_code),
                    error=error,
                )
            self.outbox.acknowledge([event.event_id for event in events])
            _diagnostic(
                logging.INFO,
                "ingest_delivery_succeeded",
                count=len(events),
                status_code=int(response.status_code),
            )
            return DeliveryResult(
                attempted=len(events),
                delivered=len(events),
                status_code=int(response.status_code),
            )

        error = f"HTTP {response.status_code}: {response.text[:1000]}"
        self.outbox.mark_failed(
            events,
            error,
            retry_base_s=self.retry_base_s,
            retry_max_s=self.retry_max_s,
        )
        _diagnostic(
            logging.WARNING,
            "ingest_delivery_rejected",
            count=len(events),
            status_code=int(response.status_code),
            error=error,
        )
        return DeliveryResult(
            attempted=len(events),
            delivered=0,
            status_code=int(response.status_code),
            error=error,
        )

    def run(self, stop_event: threading.Event, *, idle_wait_s: float = 1.0) -> None:
        while not stop_event.is_set():
            result = self.deliver_once()
            if result.attempted == 0 or result.delivered == 0:
                stop_event.wait(idle_wait_s)


def _close_client(client: SensorClient | None) -> None:
    if client is None:
        return
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.exception("Failed to close sensor client %s", client)


class SensorWorker:
    """One independently scheduled, reconnecting physical-device worker."""

    def __init__(
        self,
        *,
        spec: ClientSpec,
        outbox: SQLiteOutbox,
        agent_id: str,
        reconnect_initial_s: float = 1.0,
        reconnect_max_s: float = 60.0,
    ) -> None:
        self.spec = spec
        self.outbox = outbox
        self.agent_id = agent_id
        self.reconnect_initial_s = reconnect_initial_s
        self.reconnect_max_s = reconnect_max_s
        self._client: SensorClient | None = None
        self._client_lock = threading.Lock()

    def _set_client(self, client: SensorClient | None) -> None:
        with self._client_lock:
            self._client = client

    def close(self) -> None:
        with self._client_lock:
            client = self._client
            self._client = None
        _close_client(client)

    def _persist(
        self,
        events: Sequence[Mapping[str, Any]],
        stop_event: threading.Event,
    ) -> bool:
        if not events:
            return True
        delay = self.reconnect_initial_s
        while not stop_event.is_set():
            try:
                inserted, duplicates = self.outbox.enqueue(events)
                _diagnostic(
                    logging.INFO,
                    "sensor_events_queued",
                    worker=self.spec.name,
                    inserted=inserted,
                    duplicates=duplicates,
                    pending=self.outbox.count(),
                )
                return True
            except Exception as exc:
                _diagnostic(
                    logging.ERROR,
                    "outbox_write_failed",
                    worker=self.spec.name,
                    error=f"{type(exc).__name__}: {exc}",
                    retry_s=delay,
                )
                if stop_event.wait(delay):
                    return False
                delay = min(self.reconnect_max_s, delay * 2)
        return False

    def poll_client(
        self,
        client: SensorClient,
        *,
        stop_event: threading.Event,
    ) -> int:
        try:
            readings = list(client.poll())
            source = _source_for(client, self.spec.name)
            events = readings_to_events(
                readings,
                agent_id=self.agent_id,
                source=source,
                spectrum_wavelength_start=self.spec.spectrum_wavelength_start,
                spectrum_wavelength_step=self.spec.spectrum_wavelength_step,
            )
            persisted = self._persist(events, stop_event)
            if not persisted:
                raise SensorPollError("stopped before observations were queued")
            acknowledge = getattr(client, "acknowledge", None)
            if callable(acknowledge):
                acknowledge()
        except Exception:
            reject = getattr(client, "reject", None)
            if callable(reject):
                reject()
            raise

        client_error = getattr(client, "last_error", None)
        if client_error:
            raise SensorPollError(str(client_error))
        if not readings and self.spec.empty_is_error:
            raise SensorPollError("poll returned no readings")
        return len(events)

    def poll_once(self) -> dict[str, Any]:
        client: SensorClient | None = None
        stop_event = threading.Event()
        try:
            client = self.spec.factory()
            self._set_client(client)
            queued = self.poll_client(client, stop_event=stop_event)
            return _diagnostic(
                logging.INFO,
                "sensor_poll_succeeded",
                worker=self.spec.name,
                queued=queued,
                source=_source_for(client, self.spec.name),
            )
        except Exception as exc:
            return _diagnostic(
                logging.ERROR,
                "sensor_poll_failed",
                worker=self.spec.name,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            self.close()

    def run(self, stop_event: threading.Event) -> None:
        reconnect_delay = self.reconnect_initial_s
        client: SensorClient | None = None
        while not stop_event.is_set():
            try:
                if client is None:
                    client = self.spec.factory()
                    self._set_client(client)
                    _diagnostic(
                        logging.INFO,
                        "sensor_connected",
                        worker=self.spec.name,
                        source=_source_for(client, self.spec.name),
                    )

                queued = self.poll_client(client, stop_event=stop_event)
                reconnect_delay = self.reconnect_initial_s
                _diagnostic(
                    logging.INFO if queued else logging.DEBUG,
                    "sensor_poll_succeeded",
                    worker=self.spec.name,
                    queued=queued,
                    source=_source_for(client, self.spec.name),
                )
                if stop_event.wait(self.spec.interval_s):
                    break
            except Exception as exc:
                _diagnostic(
                    logging.WARNING,
                    "sensor_poll_failed",
                    worker=self.spec.name,
                    error=f"{type(exc).__name__}: {exc}",
                    retry_s=reconnect_delay,
                )
                _close_client(client)
                client = None
                self._set_client(None)
                if stop_event.wait(reconnect_delay):
                    break
                reconnect_delay = min(self.reconnect_max_s, reconnect_delay * 2)
        _close_client(client)
        self._set_client(None)


class HostSensorAgent:
    """Coordinates independent device workers and the durable sender."""

    def __init__(
        self,
        *,
        specs: Sequence[ClientSpec],
        outbox: SQLiteOutbox,
        sender: OutboxSender,
        agent_id: str,
        reconnect_initial_s: float = 1.0,
        reconnect_max_s: float = 60.0,
    ) -> None:
        self.outbox = outbox
        self.sender = sender
        self.stop_event = threading.Event()
        self.workers = [
            SensorWorker(
                spec=spec,
                outbox=outbox,
                agent_id=agent_id,
                reconnect_initial_s=reconnect_initial_s,
                reconnect_max_s=reconnect_max_s,
            )
            for spec in specs
        ]
        self._threads: list[threading.Thread] = []

    def poll_once(self) -> list[dict[str, Any]]:
        return [worker.poll_once() for worker in self.workers]

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("Host sensor agent is already running")
        self.stop_event.clear()
        sender_thread = threading.Thread(
            target=self.sender.run,
            args=(self.stop_event,),
            name="sensor-outbox-sender",
            daemon=False,
        )
        sender_thread.start()
        self._threads.append(sender_thread)

        for worker in self.workers:
            thread = threading.Thread(
                target=worker.run,
                args=(self.stop_event,),
                name=f"sensor-{worker.spec.name}",
                daemon=False,
            )
            thread.start()
            self._threads.append(thread)
        _diagnostic(
            logging.INFO,
            "host_sensor_agent_started",
            workers=len(self.workers),
            pending=self.outbox.count(),
        )

    def stop(self, *, timeout_s: float = 10.0) -> None:
        self.stop_event.set()
        for worker in self.workers:
            worker.close()
        deadline = time.monotonic() + timeout_s
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = [thread.name for thread in self._threads if thread.is_alive()]
        self._threads = []
        _diagnostic(
            logging.WARNING if alive else logging.INFO,
            "host_sensor_agent_stopped",
            pending=self.outbox.count(),
            threads_still_alive=alive,
        )


def serial_port_inventory() -> list[dict[str, Any]]:
    """Return JSON-compatible, metadata-only serial discovery output."""
    return [port.as_dict() for port in enumerate_serial_ports()]
