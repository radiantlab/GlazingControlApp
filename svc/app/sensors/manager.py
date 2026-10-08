# app/sensors/manager.py
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import List

from app.config import (
    CONFIG_DIR,
    DATA_DIR,
    ENVIRONMENT,
    SENSOR_INPUT_DIR,
    SENSOR_ACQUISITION,
    SENSOR_INGEST_TOKEN,
    SENSORS_CONFIG_FILE,
    Environment,
    SensorAcquisition,
)
from app.state import (
    fetch_sensor_ingest_status,
    ingest_sensor_events,
    prune_sensors_to_ids,
    register_sensor,
)

from .eko_cbox_modbus_tcp_client import EkoCBoxModbusTcpClient
from .eko_ms90_plus_sim_client import EkoMs90PlusSimClient
from .interface import SensorClient, SensorReading
from .ingestion import readings_to_ingest_events
from .jeti_specfirm_client import JetiSpecfirmClient
from .jeti_spectraval_sim import JetiSpectravalSimClient
from .jeti_spectraval_watcher import JetiSpectravalFileWatcher
from .serial_discovery import (
    InvalidSerialPortSelector,
    SerialDiscoveryError,
    SerialPortSelector,
    resolve_serial_port,
)
from .t10a_client import T10AClient, T10AHeadConfig
from .t10a_sim_client import T10ASimClient

logger = logging.getLogger(__name__)

_SVC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_workers: list[threading.Thread] = []
_clients: list[SensorClient] = []
_stop_flag = False
_sensor_errors: dict[str, str] = {}
_sensor_errors_lock = threading.Lock()


class SensorConfigurationError(RuntimeError):
    """Raised when sensor configuration is missing or unsafe."""


def _default_jeti_baudrate(dev_cfg: dict) -> int:
    explicit_baudrate = dev_cfg.get("baudrate")
    if explicit_baudrate not in (None, ""):
        return int(explicit_baudrate)

    fingerprint = " ".join(
        str(dev_cfg.get(key, ""))
        for key in ("device_id", "sensor_id", "label", "device_model", "model")
    ).lower()
    if "specbos" in fingerprint:
        return 115200
    return 921600


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def get_sensor_source() -> str:
    if ENVIRONMENT is Environment.PRODUCTION:
        return "physical"
    physical_overrides = (
        "SVC_DEVELOPMENT_USE_PHYSICAL_T10A",
        "SVC_DEVELOPMENT_USE_PHYSICAL_JETI",
        "SVC_DEVELOPMENT_USE_PHYSICAL_EKO",
    )
    return "mixed" if any(_env_flag(name) for name in physical_overrides) else "simulated"


def _set_sensor_error(sensor_id: str, error: object) -> None:
    with _sensor_errors_lock:
        _sensor_errors[sensor_id] = str(error)


def _clear_sensor_error(sensor_id: str) -> None:
    with _sensor_errors_lock:
        _sensor_errors.pop(sensor_id, None)


def get_sensor_health() -> tuple[str, list[str]]:
    with _sensor_errors_lock:
        errors = [
            f"{sensor_id}: {message}"
            for sensor_id, message in sorted(_sensor_errors.items())
        ]

    now = time.time()
    for item in fetch_sensor_ingest_status():
        if (
            SENSOR_ACQUISITION is not SensorAcquisition.EXTERNAL
            and item.get("acquisition") != SensorAcquisition.EXTERNAL.value
        ):
            continue
        sensor_id = item["sensor_id"]
        received_ts = item.get("received_ts")
        if received_ts is None:
            errors.append(
                f"{sensor_id}: no observation received from the external Sensor Agent"
            )
            continue
        # The status helper supplies the configured threshold when present.
        stale_after_s = float(item.get("stale_after_s") or 180.0)
        age_s = max(0.0, now - float(received_ts))
        if age_s >= stale_after_s:
            errors.append(
                f"{sensor_id}: external observation is {age_s:.0f}s old "
                f"(stale threshold {stale_after_s:.0f}s)"
            )
    return ("degraded" if errors else "healthy", errors)


def _load_config() -> dict:
    """
    Expected JSON structure (keys optional):

    {
      "t10a": [ ... ],
      "jeti_spectraval": [ ... ],
      "eko_ms90_plus": [ ... ]
    }
    """
    config_path = SENSORS_CONFIG_FILE
    if not os.path.exists(config_path):
        raise SensorConfigurationError(
            f"Sensor configuration does not exist: {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as exc:
            raise SensorConfigurationError(
                f"Sensor configuration is invalid JSON: {config_path}: {exc}"
            ) from exc
    if not isinstance(config, dict):
        raise SensorConfigurationError("Sensor configuration must be a JSON object")
    return config


def _require_list(config: dict, key: str) -> list[dict]:
    value = config.get(key, [])
    if not isinstance(value, list):
        raise SensorConfigurationError(f"{key} must be a JSON array")
    if any(not isinstance(item, dict) for item in value):
        raise SensorConfigurationError(f"Every {key} entry must be a JSON object")
    if len(value) > 4:
        raise SensorConfigurationError(f"{key} supports at most four devices")
    return value


def _is_enabled(item: dict) -> bool:
    enabled = item.get("enabled", True)
    if not isinstance(enabled, bool):
        raise SensorConfigurationError("Sensor enabled must be true or false")
    return enabled


def _path_is_within(raw_path: str, root: str) -> bool:
    path = Path(raw_path)
    if not path.is_absolute():
        if path.parts and path.parts[0].lower() in {"data", "sensor-input"}:
            path = Path(*path.parts[1:])
        path = Path(root) / path
    try:
        path.resolve(strict=False).relative_to(Path(root).resolve(strict=False))
        return True
    except ValueError:
        return False


def _path_is_within_data_dir(raw_path: str) -> bool:
    return _path_is_within(raw_path, DATA_DIR)


def _resolve_data_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        # Preserve existing site configs whose paths were written as data/foo.cap
        # when /app/svc/data was resolved relative to the service directory.
        if path.parts and path.parts[0].lower() == "data":
            path = Path(*path.parts[1:])
        path = Path(DATA_DIR) / path
    return str(path.resolve(strict=False))


def _resolve_sensor_input_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        if path.parts and path.parts[0].lower() == "sensor-input":
            path = Path(*path.parts[1:])
        path = Path(SENSOR_INPUT_DIR) / path
    return str(path.resolve(strict=False))


def _resolve_config_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(CONFIG_DIR) / path
    return str(path.resolve(strict=False))


def _device_acquisition(dev_cfg: dict) -> SensorAcquisition:
    """Return who reads a device: this process or the external Sensor Agent.

    SVC_SENSOR_ACQUISITION=external hands every device to the agent. Under
    embedded, a single device can still opt out with "acquisition": "external",
    which is how COM-port sensors reach a container that cannot open them.
    """
    if SENSOR_ACQUISITION is SensorAcquisition.EXTERNAL:
        return SensorAcquisition.EXTERNAL
    raw = str(dev_cfg.get("acquisition") or SensorAcquisition.EMBEDDED.value)
    return SensorAcquisition(raw.strip().lower())


def validate_sensor_configuration() -> dict:
    """Validate the complete environment-specific sensor configuration."""
    config = _load_config()
    t10a_configs = _require_list(config, "t10a")
    jeti_configs = _require_list(config, "jeti_spectraval")
    eko_configs = _require_list(config, "eko_ms90_plus")

    for family, items in (
        ("t10a", t10a_configs),
        ("jeti_spectraval", jeti_configs),
        ("eko_ms90_plus", eko_configs),
    ):
        for item in items:
            try:
                _device_acquisition(item)
            except ValueError as exc:
                raise SensorConfigurationError(
                    f"{family} entry {item.get('device_id') or item.get('sensor_id')} "
                    "has an invalid acquisition value; use embedded or external"
                ) from exc
            if (
                SENSOR_ACQUISITION is SensorAcquisition.EMBEDDED
                and _is_enabled(item)
                and _device_acquisition(item) is SensorAcquisition.EXTERNAL
                and not SENSOR_INGEST_TOKEN
            ):
                # Without a token /sensors/ingest answers 404, so the agent's
                # readings would never arrive. Global external mode already
                # requires the token in app.config.
                raise SensorConfigurationError(
                    f"{family} entry {item.get('device_id') or item.get('sensor_id')} "
                    "is marked external; set SVC_SENSOR_INGEST_TOKEN so the "
                    "Sensor Agent can post its readings"
                )

    for item in t10a_configs:
        if not _is_enabled(item):
            continue
        if not item.get("device_id"):
            raise SensorConfigurationError("Every T-10A entry requires device_id")
        heads = item.get("heads")
        if not isinstance(heads, list) or not heads:
            raise SensorConfigurationError(
                f"T-10A {item.get('device_id')} requires at least one head"
            )
        for head in heads:
            if (
                not isinstance(head, dict)
                or "head_no" not in head
                or not head.get("sensor_id")
            ):
                raise SensorConfigurationError(
                    f"T-10A {item.get('device_id')} has an invalid head entry"
                )
            try:
                int(head["head_no"])
            except (TypeError, ValueError) as exc:
                raise SensorConfigurationError(
                    f"T-10A {item.get('device_id')} head_no must be an integer"
                ) from exc
        try:
            float(item.get("interval_s", 60.0))
            float(item.get("timeout_s", 1.0))
            int(item.get("baudrate", 9600))
        except (TypeError, ValueError) as exc:
            raise SensorConfigurationError(
                f"T-10A {item.get('device_id')} has invalid timing or baudrate values"
            ) from exc
        if ENVIRONMENT is Environment.PRODUCTION and (
            not item.get("port") or str(item.get("port")).upper() == "SIM"
        ):
            raise SensorConfigurationError(
                f"Production T-10A {item.get('device_id')} requires a physical port"
            )
        if ENVIRONMENT is Environment.PRODUCTION:
            try:
                SerialPortSelector.from_config(item)
            except InvalidSerialPortSelector as exc:
                raise SensorConfigurationError(
                    f"Production T-10A {item.get('device_id')} has an invalid "
                    f"serial-port selector: {exc}"
                ) from exc

    for item in jeti_configs:
        if not _is_enabled(item):
            continue
        sensor_id = item.get("sensor_id", "JETI-00")
        transport = str(item.get("transport", "file")).lower()
        try:
            float(item.get("interval_s", 60.0))
            float(item.get("watch_interval_s", 1.0))
        except (TypeError, ValueError) as exc:
            raise SensorConfigurationError(
                f"JETI {sensor_id} has invalid interval values"
            ) from exc
        if transport in {"serial_scpi", "serial", "specfirm"}:
            if not item.get("port"):
                raise SensorConfigurationError(
                    f"JETI {sensor_id} serial transport requires a physical port"
                )
            if ENVIRONMENT is Environment.PRODUCTION:
                try:
                    SerialPortSelector.from_config(item)
                except InvalidSerialPortSelector as exc:
                    raise SensorConfigurationError(
                        f"Production JETI {sensor_id} has an invalid serial-port "
                        f"selector: {exc}"
                    ) from exc
            try:
                _default_jeti_baudrate(item)
                float(item.get("timeout_s", 1.0))
                float(item.get("tint_ms", 100.0))
                int(item.get("avg_count", 1))
            except (TypeError, ValueError) as exc:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} has invalid serial settings"
                ) from exc
        elif transport == "file":
            input_path = str(
                item.get("input_path") or item.get("output_path") or ""
            )
            if not input_path:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} file transport requires input_path"
                )
            uses_legacy_output_path = not item.get("input_path")
            allowed_root = DATA_DIR if uses_legacy_output_path else SENSOR_INPUT_DIR
            if not _path_is_within(input_path, allowed_root):
                raise SensorConfigurationError(
                    f"JETI {sensor_id} input path must be inside "
                    + (
                        "SVC_DATA_DIR"
                        if uses_legacy_output_path
                        else "SVC_SENSOR_INPUT_DIR"
                    )
                )
            if ENVIRONMENT is Environment.DEVELOPMENT and not item.get("template_path"):
                raise SensorConfigurationError(
                    f"Development JETI {sensor_id} requires template_path"
                )
            try:
                max_records = int(item.get("max_records_per_poll", 250))
                max_read_bytes = int(item.get("max_read_bytes", 4 * 1024 * 1024))
                if max_records <= 0 or max_read_bytes <= 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} backfill limits must be positive integers"
                ) from exc
            initial_position = str(item.get("initial_position", "end")).lower()
            if initial_position not in {"beginning", "end"}:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} initial_position must be beginning or end"
                )
            input_kind = str(item.get("input_kind", "auto")).lower()
            if input_kind not in {"auto", "file", "directory"}:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} input_kind must be auto, file, or directory"
                )
        else:
            raise SensorConfigurationError(
                f"JETI {sensor_id} uses unsupported transport {transport!r}"
            )

    for item in eko_configs:
        if not _is_enabled(item):
            continue
        sensor_id = item.get("sensor_id", "EKO-00")
        if ENVIRONMENT is Environment.PRODUCTION and not item.get("host"):
            raise SensorConfigurationError(
                f"Production EKO {sensor_id} requires host"
            )
        try:
            port = int(item.get("port", 502))
            if not 1 <= port <= 65535:
                raise ValueError
            int(item.get("slave_address", 1))
            float(item.get("timeout_s", 3.0))
        except (TypeError, ValueError) as exc:
            raise SensorConfigurationError(
                f"EKO {sensor_id} has invalid port, slave_address, or timeout_s"
            ) from exc

    return config


def _make_clients_from_config() -> list[tuple[SensorClient, float]]:
    cfg = validate_sensor_configuration()
    clients_with_interval: list[tuple[SensorClient, float]] = []
    configured_sensor_ids: set[str] = set()

    is_development = ENVIRONMENT is Environment.DEVELOPMENT
    is_production = ENVIRONMENT is Environment.PRODUCTION
    development_uses_physical_t10a = _env_flag(
        "SVC_DEVELOPMENT_USE_PHYSICAL_T10A"
    )
    development_uses_physical_jeti = _env_flag(
        "SVC_DEVELOPMENT_USE_PHYSICAL_JETI"
    )
    development_uses_physical_eko = _env_flag(
        "SVC_DEVELOPMENT_USE_PHYSICAL_EKO"
    )
    if is_development and any(
        (
            development_uses_physical_t10a,
            development_uses_physical_jeti,
            development_uses_physical_eko,
        )
    ):
        logger.warning(
            "DEVELOPMENT HARDWARE OVERRIDE ACTIVE: physical sensor access is enabled"
        )

    # --- T-10A -------------------------------------------------------------
    t10a_configs = cfg.get("t10a", [])[:4]  # enforce 1-4 devices
    use_physical_t10a = is_production or (
        is_development and development_uses_physical_t10a
    )
    if is_development and not development_uses_physical_t10a and t10a_configs:
        logger.info(
            "Development: using simulated T10A data for %d config(s). "
            "Set SVC_DEVELOPMENT_USE_PHYSICAL_T10A=true for explicit hardware testing.",
            len(t10a_configs),
        )

    for dev_cfg in t10a_configs:
        if not _is_enabled(dev_cfg):
            continue
        device_id = dev_cfg["device_id"]
        requested_port = str(dev_cfg.get("port") or "")
        port = requested_port
        interval_s = float(dev_cfg.get("interval_s", 60.0))
        timeout_s = float(dev_cfg.get("timeout_s", 1.0))
        protocol_cfg = dev_cfg.get("protocol", {})
        acquisition = _device_acquisition(dev_cfg)

        if use_physical_t10a and (not port or port == "SIM"):
            logger.warning(
                "Skip T10A device %s: physical operation requires a USB COM port",
                device_id,
            )
            continue

        heads_cfg: list[T10AHeadConfig] = []
        for h in dev_cfg.get("heads", []):
            hc = T10AHeadConfig(
                head_no=h["head_no"],
                sensor_id=h["sensor_id"],
                label=h.get("label", h["sensor_id"]),
                location=h.get("location"),
            )
            heads_cfg.append(hc)

            register_sensor(
                sensor_id=hc.sensor_id,
                kind="t10a",
                label=hc.label,
                location=hc.location,
                config={
                    "device_id": device_id,
                    "port": port or "SIM",
                    "head_no": hc.head_no,
                    "interval_s": interval_s,
                    "timeout_s": timeout_s,
                    "protocol": protocol_cfg,
                    "acquisition": acquisition.value,
                    "custom_label": h.get("custom_label"),
                    "device_custom_label": dev_cfg.get("custom_label"),
                },
            )
            configured_sensor_ids.add(hc.sensor_id)

        if not heads_cfg:
            continue

        if acquisition is SensorAcquisition.EXTERNAL:
            logger.info(
                "External Sensor Agent owns T10A device %s; API registered %d head(s)",
                device_id,
                len(heads_cfg),
            )
            continue

        if use_physical_t10a:
            try:
                port_info = resolve_serial_port(dev_cfg)
                port = port_info.device
                logger.info(
                    "Resolved T10A device %s from %s to %s (%s)",
                    device_id,
                    requested_port or "auto",
                    port,
                    port_info.hwid or port_info.description or "no hardware metadata",
                )
                for hc in heads_cfg:
                    register_sensor(
                        sensor_id=hc.sensor_id,
                        kind="t10a",
                        label=hc.label,
                        location=hc.location,
                        config={
                            "device_id": device_id,
                            "configured_port": requested_port or "auto",
                            "port": port,
                            "port_identity": dev_cfg.get("port_identity", {}),
                            "resolved_port_identity": port_info.as_dict(),
                            "head_no": hc.head_no,
                            "interval_s": interval_s,
                            "timeout_s": timeout_s,
                            "protocol": protocol_cfg,
                        },
                    )
                client = T10AClient(
                    device_id=device_id,
                    port=port,
                    heads=heads_cfg,
                    timeout_s=timeout_s,
                    protocol=protocol_cfg,
                    baudrate=int(dev_cfg.get("baudrate", 9600)),
                )
                clients_with_interval.append((client, interval_s))
            except (InvalidSerialPortSelector, SerialDiscoveryError, OSError) as e:
                logger.warning("Skip T10A device %s (port %s): %s", device_id, port, e)
                _set_sensor_error(device_id, e)
            except Exception as e:
                logger.warning("Skip T10A device %s (port %s): %s", device_id, port, e)
                _set_sensor_error(device_id, e)
        elif is_development:
            clients_with_interval.append(
                (
                    T10ASimClient(
                        device_id=device_id,
                        heads=heads_cfg,
                    ),
                    interval_s,
                )
            )
        else:
            logger.warning(
                "Skip T10A device %s: unsupported environment=%s",
                device_id,
                ENVIRONMENT.value,
            )

    # --- JETI spectraval ---------------------------------------------------
    # Supported transports:
    #   - file (default): watcher of LiVal capture text, plus a writer in development
    #   - serial_scpi: direct SPECFIRM serial polling
    for dev_cfg in cfg.get("jeti_spectraval", [])[:4]:
        if not _is_enabled(dev_cfg):
            continue
        sensor_id = dev_cfg.get("sensor_id", "JETI-00")
        device_id = dev_cfg.get("device_id", "JETI")
        interval_s = float(dev_cfg.get("interval_s", 60.0))
        label = dev_cfg.get("label", sensor_id)
        location = dev_cfg.get("location")

        transport = str(dev_cfg.get("transport", "file")).lower()
        if transport in {"serial_scpi", "serial", "specfirm"}:
            if is_development and not development_uses_physical_jeti:
                logger.info(
                    "Development: skipping physical JETI serial config for %s. "
                    "Set SVC_DEVELOPMENT_USE_PHYSICAL_JETI=true to enable it.",
                    sensor_id,
                )
                continue

            requested_port = str(dev_cfg.get("port") or "")
            if not requested_port:
                logger.warning("Skip JETI serial_scpi %s: missing 'port'", sensor_id)
                continue

            baudrate = _default_jeti_baudrate(dev_cfg)
            timeout_s = float(dev_cfg.get("timeout_s", 1.0))
            tint_ms = float(dev_cfg.get("tint_ms", 100.0))
            avg_count = int(dev_cfg.get("avg_count", 1))
            w_start = int(dev_cfg.get("wavelength_start_nm", 380))
            w_end = int(dev_cfg.get("wavelength_end_nm", 780))
            w_step = int(dev_cfg.get("wavelength_step_nm", 1))

            if _device_acquisition(dev_cfg) is SensorAcquisition.EXTERNAL:
                register_sensor(
                    sensor_id=sensor_id,
                    kind="jeti_spectraval",
                    label=label,
                    location=location,
                    config={
                        "device_id": device_id,
                        "transport": "serial_scpi",
                        "configured_port": requested_port or "auto",
                        "port_identity": dev_cfg.get("port_identity", {}),
                        "baudrate": baudrate,
                        "timeout_s": timeout_s,
                        "tint_ms": tint_ms,
                        "avg_count": avg_count,
                        "wavelength_start_nm": w_start,
                        "wavelength_end_nm": w_end,
                        "wavelength_step_nm": w_step,
                        "acquisition": "external",
                    },
                )
                configured_sensor_ids.add(sensor_id)
                logger.info(
                    "External Sensor Agent owns JETI serial device %s",
                    device_id,
                )
                continue

            try:
                port_info = resolve_serial_port(dev_cfg)
                port = port_info.device
                logger.info(
                    "Resolved JETI device %s from %s to %s (%s)",
                    device_id,
                    requested_port or "auto",
                    port,
                    port_info.hwid or port_info.description or "no hardware metadata",
                )
                register_sensor(
                    sensor_id=sensor_id,
                    kind="jeti_spectraval",
                    label=label,
                    location=location,
                    config={
                        "device_id": device_id,
                        "transport": "serial_scpi",
                        "configured_port": requested_port or "auto",
                        "port": port,
                        "port_identity": dev_cfg.get("port_identity", {}),
                        "resolved_port_identity": port_info.as_dict(),
                        "baudrate": baudrate,
                        "timeout_s": timeout_s,
                        "tint_ms": tint_ms,
                        "avg_count": avg_count,
                        "wavelength_start_nm": w_start,
                        "wavelength_end_nm": w_end,
                        "wavelength_step_nm": w_step,
                    },
                )
                configured_sensor_ids.add(sensor_id)

                serial_client = JetiSpecfirmClient(
                    device_id=device_id,
                    sensor_id=sensor_id,
                    port=port,
                    label=label,
                    location=location,
                    baudrate=baudrate,
                    timeout_s=timeout_s,
                    tint_ms=tint_ms,
                    avg_count=avg_count,
                    wavelength_start_nm=w_start,
                    wavelength_end_nm=w_end,
                    wavelength_step_nm=w_step,
                )
                clients_with_interval.append((serial_client, interval_s))
            except Exception as e:
                logger.warning("Skip JETI serial_scpi %s: %s", sensor_id, e)
                _set_sensor_error(sensor_id, e)

            continue

        # Default/file watcher transport.
        raw_template_path = str(dev_cfg.get("template_path", ""))
        raw_input_path = str(
            dev_cfg.get("input_path") or dev_cfg.get("output_path") or ""
        )
        if not raw_input_path:
            logger.warning("Skip JETI %s: missing 'input_path'", sensor_id)
            continue
        template_path = (
            _resolve_config_path(raw_template_path) if raw_template_path else ""
        )
        uses_legacy_output_path = not dev_cfg.get("input_path")
        input_path = (
            _resolve_data_path(raw_input_path)
            if uses_legacy_output_path
            else _resolve_sensor_input_path(raw_input_path)
        )

        loop = bool(dev_cfg.get("loop", True))
        watch_interval_s = float(dev_cfg.get("watch_interval_s", 1.0))
        stale_after_s = float(
            dev_cfg.get("stale_after_s", max(interval_s * 3.0, 60.0))
        )
        cursor_dir = _resolve_data_path(
            str(dev_cfg.get("cursor_dir", ".sensor-cursors"))
        )

        try:
            register_sensor(
                sensor_id=sensor_id,
                kind="jeti_spectraval",
                label=label,
                location=location,
                config={
                    "device_id": device_id,
                    "transport": "file",
                    "template_path": template_path,
                    "input_path": input_path,
                    "interval_s": interval_s,
                    "watch_interval_s": watch_interval_s,
                    "stale_after_s": stale_after_s,
                    "initial_position": str(
                        dev_cfg.get("initial_position", "end")
                    ).lower(),
                    "max_records_per_poll": int(
                        dev_cfg.get("max_records_per_poll", 250)
                    ),
                    "max_read_bytes": int(
                        dev_cfg.get("max_read_bytes", 4 * 1024 * 1024)
                    ),
                    "source_timezone": dev_cfg.get("source_timezone"),
                    "acquisition": _device_acquisition(dev_cfg).value,
                    "loop": loop,
                },
            )
            configured_sensor_ids.add(sensor_id)

            if _device_acquisition(dev_cfg) is SensorAcquisition.EXTERNAL:
                logger.info(
                    "External Sensor Agent owns JETI file source %s",
                    device_id,
                )
                continue

            watcher = JetiSpectravalFileWatcher(
                device_id=device_id,
                sensor_id=sensor_id,
                input_path=input_path,
                label=label,
                location=location,
                svc_root=_SVC_DIR,
                input_kind=str(dev_cfg.get("input_kind", "auto")),
                cursor_dir=cursor_dir,
                initial_position=str(dev_cfg.get("initial_position", "end")),
                max_records_per_poll=int(
                    dev_cfg.get("max_records_per_poll", 250)
                ),
                max_read_bytes=int(
                    dev_cfg.get("max_read_bytes", 4 * 1024 * 1024)
                ),
                source_timezone=dev_cfg.get("source_timezone"),
            )
            watcher.stale_after_s = stale_after_s
            clients_with_interval.append((watcher, watch_interval_s))

            if is_development:
                output_path = _resolve_data_path(
                    str(dev_cfg.get("output_path") or raw_input_path)
                )
                sim = JetiSpectravalSimClient(
                    device_id=device_id,
                    sensor_id=sensor_id,
                    template_path=template_path,
                    output_path=output_path,
                    label=label + " (Sim Writer)",
                    interval_s=interval_s,
                    loop=loop,
                    location=location,
                    svc_root=_SVC_DIR,
                )
                clients_with_interval.append((sim, interval_s))

        except Exception as e:
            logger.warning("Skip Jeti Spectraval %s: %s", sensor_id, e)
            _set_sensor_error(sensor_id, e)

    # --- EKO MS-90+ (via C-BOX Ethernet Modbus TCP) -----------------------
    eko_configs = cfg.get("eko_ms90_plus", [])[:4]
    use_physical_eko = is_production or (
        is_development and development_uses_physical_eko
    )
    if is_development and not development_uses_physical_eko and eko_configs:
        logger.info(
            "Development: using simulated EKO MS-90+ data for %d config(s). "
            "Set SVC_DEVELOPMENT_USE_PHYSICAL_EKO=true for explicit hardware testing.",
            len(eko_configs),
        )

    for dev_cfg in eko_configs:
        if not _is_enabled(dev_cfg):
            continue
        sensor_id = dev_cfg.get("sensor_id", "EKO-00")
        device_id = dev_cfg.get("device_id", "EKO-CBOX")
        label = dev_cfg.get("label", sensor_id)
        location = dev_cfg.get("location")
        interval_s = float(dev_cfg.get("interval_s", 5.0))
        host = str(dev_cfg.get("host") or "").strip()
        raw_tcp_port = dev_cfg.get("port", 502)
        raw_slave_address = dev_cfg.get("slave_address", 1)
        raw_timeout_s = dev_cfg.get("timeout_s", 3.0)
        float_byte_order = str(dev_cfg.get("float_byte_order", "ABCD"))
        stale_after_s = float(
            dev_cfg.get("stale_after_s", max(interval_s * 3.0, 30.0))
        )

        if use_physical_eko:
            if not host:
                logger.warning(
                    "Skip EKO MS-90+ %s: physical operation requires the C-BOX IP address",
                    sensor_id,
                )
                continue

            try:
                tcp_port = int(raw_tcp_port)
                slave_address = int(raw_slave_address)
                timeout_s = float(raw_timeout_s)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "Skip EKO MS-90+ %s: invalid Modbus TCP config "
                    "(port=%r, slave_address=%r, timeout_s=%r): %s",
                    sensor_id,
                    raw_tcp_port,
                    raw_slave_address,
                    raw_timeout_s,
                    e,
                )
                continue
        else:
            tcp_port = raw_tcp_port
            slave_address = raw_slave_address
            timeout_s = raw_timeout_s

        try:
            register_sensor(
                sensor_id=sensor_id,
                kind="eko_ms90_plus",
                label=label,
                location=location,
                config={
                    "device_id": device_id,
                    "host": host,
                    "port": tcp_port,
                    "slave_address": slave_address,
                    "interval_s": interval_s,
                    "stale_after_s": stale_after_s,
                    "timeout_s": timeout_s,
                    "float_byte_order": float_byte_order,
                    "acquisition": _device_acquisition(dev_cfg).value,
                },
            )
            configured_sensor_ids.add(sensor_id)

            if _device_acquisition(dev_cfg) is SensorAcquisition.EXTERNAL:
                logger.info(
                    "External Sensor Agent owns EKO device %s at %s:%s",
                    device_id,
                    host,
                    tcp_port,
                )
                continue

            if use_physical_eko:
                eko_client = EkoCBoxModbusTcpClient(
                    device_id=device_id,
                    sensor_id=sensor_id,
                    host=host,
                    port=tcp_port,
                    slave_address=slave_address,
                    timeout_s=timeout_s,
                    label=label,
                    location=location,
                    float_byte_order=float_byte_order,
                )
                eko_client.stale_after_s = stale_after_s
                clients_with_interval.append((eko_client, interval_s))
            elif is_development:
                sim_lat = float(dev_cfg.get("latitude_deg", 44.5646))
                sim_lon = float(dev_cfg.get("longitude_deg", -123.2620))
                clients_with_interval.append(
                    (
                        EkoMs90PlusSimClient(
                            device_id=device_id,
                            sensor_id=sensor_id,
                            latitude_deg=sim_lat,
                            longitude_deg=sim_lon,
                        ),
                        interval_s,
                    )
                )
            else:
                logger.warning(
                    "Skip EKO MS-90+ %s: unsupported environment=%s",
                    sensor_id,
                    ENVIRONMENT.value,
                )
        except Exception as e:
            logger.warning("Skip EKO MS-90+ %s: %s", sensor_id, e)
            _set_sensor_error(sensor_id, e)

    # This only marks removed sensors inactive; it never deletes readings or
    # spectra. Production history remains durable across config changes.
    prune_sensors_to_ids(list(configured_sensor_ids))
    return clients_with_interval


def _poll_and_persist(client: SensorClient) -> List[SensorReading]:
    """Persist one client poll atomically, then acknowledge its source cursor."""
    client_id = str(getattr(client, "id", client))
    try:
        readings: List[SensorReading] = list(client.poll())
        events = readings_to_ingest_events(
            readings,
            event_namespace="container",
            source=f"container:{client_id}",
            spectrum_wavelength_start=int(
                getattr(client, "spectrum_wavelength_start", 380)
            ),
            spectrum_wavelength_step=int(
                getattr(client, "spectrum_wavelength_step", 1)
            ),
        )
        if events:
            ingest_sensor_events(events)
        acknowledge = getattr(client, "acknowledge", None)
        if callable(acknowledge):
            acknowledge()
        return readings
    except Exception:
        reject = getattr(client, "reject", None)
        if callable(reject):
            reject()
        raise


def _worker_loop(client: SensorClient, interval_s: float) -> None:
    global _stop_flag
    logger.info(f"Sensor worker started for {client} with interval {interval_s}s")
    client_id = str(getattr(client, "id", client))
    stale_after_s = float(
        getattr(client, "stale_after_s", max(float(interval_s) * 3.0, 30.0))
    )
    started_at = time.monotonic()
    last_success_at: float | None = None

    while not _stop_flag:
        try:
            readings = _poll_and_persist(client)
        except Exception as e:
            logger.exception("Sensor worker poll failed for %s: %s", client, e)
            _set_sensor_error(client_id, e)
            readings = []
        else:
            now = time.monotonic()
            reported_error = getattr(client, "last_error", None)
            if readings:
                last_success_at = now
                logger.debug(
                    "Manager: received %d readings from %s", len(readings), client
                )
            if reported_error:
                _set_sensor_error(client_id, reported_error)
            elif readings:
                _clear_sensor_error(client_id)
            else:
                freshness_origin = last_success_at or started_at
                stale_for_s = now - freshness_origin
                if stale_for_s >= stale_after_s:
                    _set_sensor_error(
                        client_id,
                        f"no readings received for {stale_for_s:.0f}s "
                        f"(stale threshold {stale_after_s:.0f}s)",
                    )
        if _stop_flag:
            break
        time.sleep(interval_s)


def start_sensor_workers() -> None:
    """
    Called once at app startup.
    Creates clients from config and starts one worker thread per client.
    """
    global _workers, _clients, _stop_flag
    _stop_flag = False
    _workers = []
    _clients = []
    with _sensor_errors_lock:
        _sensor_errors.clear()

    clients_with_interval = _make_clients_from_config()
    _clients = [c for c, _ in clients_with_interval]

    for client, interval_s in clients_with_interval:
        t = threading.Thread(
            target=_worker_loop,
            args=(client, interval_s),
            daemon=True,
        )
        t.start()
        _workers.append(t)

    logger.info(f"Started {len(_workers)} sensor workers")


def stop_sensor_workers() -> None:
    """Called on shutdown to stop threads cleanly."""
    global _stop_flag, _workers, _clients
    _stop_flag = True

    for worker in _workers:
        worker.join(timeout=2.0)

    for client in _clients:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception as e:
                logger.warning("Failed closing sensor client %s: %s", client, e)

    _workers = []
    _clients = []


def update_sensor_labels(
    sensor_id: str,
    custom_label: str | None = None,
    device_custom_label: str | None = None,
) -> bool:
    """
    Update the custom labels for a T-10A head and/or body.
    Updates the SQLite database only.
    """
    config_path = SENSORS_CONFIG_FILE
    if not os.path.exists(config_path):
        logger.warning("No sensors_config.json found at %s", config_path)
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        logger.error("Failed to load sensors config for update: %s", e)
        return False

    found = False
    target_device_id = None

    # Loop through t10a devices to find the matching head and get its device_id
    for dev_cfg in cfg.get("t10a", []):
        for h in dev_cfg.get("heads", []):
            if h.get("sensor_id") == sensor_id:
                found = True
                target_device_id = dev_cfg.get("device_id")
                break
        if found:
            break

    if not found:
        return False

    # Update SQLite database
    from app.state import _db_connection
    import sqlite3

    try:
        with _db_connection(row_factory=sqlite3.Row) as conn:
            # First, update the head custom_label in its config_json
            row = conn.execute(
                "SELECT config_json FROM sensors WHERE id = ?", (sensor_id,)
            ).fetchone()
            if row:
                config = json.loads(row["config_json"] or "{}")
                if custom_label is not None:
                    if custom_label.strip() == "":
                        config.pop("custom_label", None)
                    else:
                        config["custom_label"] = custom_label.strip()
                
                if device_custom_label is not None:
                    if device_custom_label.strip() == "":
                        config.pop("device_custom_label", None)
                    else:
                        config["device_custom_label"] = device_custom_label.strip()
                
                conn.execute(
                    "UPDATE sensors SET config_json = ? WHERE id = ?",
                    (json.dumps(config), sensor_id),
                )

            # If device_custom_label is updated, we must update all heads belonging to this device_id
            if device_custom_label is not None and target_device_id:
                rows = conn.execute(
                    "SELECT id, config_json FROM sensors WHERE kind = 't10a'"
                ).fetchall()
                for r in rows:
                    h_id = r["id"]
                    if h_id == sensor_id:
                        continue # Already updated
                    
                    h_config = json.loads(r["config_json"] or "{}")
                    if h_config.get("device_id") == target_device_id:
                        if device_custom_label.strip() == "":
                            h_config.pop("device_custom_label", None)
                        else:
                            h_config["device_custom_label"] = device_custom_label.strip()
                        
                        conn.execute(
                            "UPDATE sensors SET config_json = ? WHERE id = ?",
                            (json.dumps(h_config), h_id),
                        )
    except Exception as e:
        logger.error("Failed to update database with custom labels: %s", e)
        return False

    return True
