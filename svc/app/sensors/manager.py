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
    SENSORS_CONFIG_FILE,
    Environment,
)
from app.state import (
    delete_sensor_readings_for_ids,
    insert_sensor_reading,
    insert_sensor_spectrum,
    prune_sensors_to_ids,
    register_sensor,
)

from .eko_cbox_modbus_tcp_client import EkoCBoxModbusTcpClient
from .eko_ms90_plus_sim_client import EkoMs90PlusSimClient
from .interface import SensorClient, SensorReading
from .jeti_specfirm_client import JetiSpecfirmClient
from .jeti_spectraval_sim import JetiSpectravalSimClient
from .jeti_spectraval_watcher import JetiSpectravalFileWatcher
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


def _path_is_within_data_dir(raw_path: str) -> bool:
    path = Path(raw_path)
    if not path.is_absolute():
        if path.parts and path.parts[0].lower() == "data":
            path = Path(*path.parts[1:])
        path = Path(DATA_DIR) / path
    try:
        path.resolve(strict=False).relative_to(Path(DATA_DIR).resolve(strict=False))
        return True
    except ValueError:
        return False


def _resolve_data_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        # Preserve existing site configs whose paths were written as data/foo.cap
        # when /app/svc/data was resolved relative to the service directory.
        if path.parts and path.parts[0].lower() == "data":
            path = Path(*path.parts[1:])
        path = Path(DATA_DIR) / path
    return str(path.resolve(strict=False))


def _resolve_config_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(CONFIG_DIR) / path
    return str(path.resolve(strict=False))


def validate_sensor_configuration() -> dict:
    """Validate the complete environment-specific sensor configuration."""
    config = _load_config()
    t10a_configs = _require_list(config, "t10a")
    jeti_configs = _require_list(config, "jeti_spectraval")
    eko_configs = _require_list(config, "eko_ms90_plus")

    for item in t10a_configs:
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

    for item in jeti_configs:
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
            output_path = str(item.get("output_path") or "")
            if not output_path:
                raise SensorConfigurationError(
                    f"JETI {sensor_id} file transport requires output_path"
                )
            if not _path_is_within_data_dir(output_path):
                raise SensorConfigurationError(
                    f"JETI {sensor_id} output_path must be inside SVC_DATA_DIR"
                )
            if ENVIRONMENT is Environment.DEVELOPMENT and not item.get("template_path"):
                raise SensorConfigurationError(
                    f"Development JETI {sensor_id} requires template_path"
                )
        else:
            raise SensorConfigurationError(
                f"JETI {sensor_id} uses unsupported transport {transport!r}"
            )

    for item in eko_configs:
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
        device_id = dev_cfg["device_id"]
        port = str(dev_cfg.get("port") or "")
        interval_s = float(dev_cfg.get("interval_s", 60.0))
        timeout_s = float(dev_cfg.get("timeout_s", 1.0))
        protocol_cfg = dev_cfg.get("protocol", {})

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
                },
            )
            configured_sensor_ids.add(hc.sensor_id)

        if not heads_cfg:
            continue

        if use_physical_t10a:
            try:
                client = T10AClient(
                    device_id=device_id,
                    port=port,
                    heads=heads_cfg,
                    timeout_s=timeout_s,
                    protocol=protocol_cfg,
                    baudrate=int(dev_cfg.get("baudrate", 9600)),
                )
                clients_with_interval.append((client, interval_s))
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
    #   - file (default): watcher of .cap output path, plus a writer in development
    #   - serial_scpi: direct SPECFIRM serial polling
    for dev_cfg in cfg.get("jeti_spectraval", [])[:4]:
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

            port = dev_cfg.get("port")
            if not port:
                logger.warning("Skip JETI serial_scpi %s: missing 'port'", sensor_id)
                continue

            baudrate = _default_jeti_baudrate(dev_cfg)
            timeout_s = float(dev_cfg.get("timeout_s", 1.0))
            tint_ms = float(dev_cfg.get("tint_ms", 100.0))
            avg_count = int(dev_cfg.get("avg_count", 1))
            w_start = int(dev_cfg.get("wavelength_start_nm", 380))
            w_end = int(dev_cfg.get("wavelength_end_nm", 780))
            w_step = int(dev_cfg.get("wavelength_step_nm", 1))

            try:
                register_sensor(
                    sensor_id=sensor_id,
                    kind="jeti_spectraval",
                    label=label,
                    location=location,
                    config={
                        "device_id": device_id,
                        "transport": "serial_scpi",
                        "port": port,
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
        raw_output_path = str(dev_cfg.get("output_path") or "")
        if not raw_output_path:
            logger.warning("Skip Jeti Spectraval %s: missing 'output_path'", sensor_id)
            continue
        template_path = (
            _resolve_config_path(raw_template_path) if raw_template_path else ""
        )
        output_path = _resolve_data_path(raw_output_path)

        loop = bool(dev_cfg.get("loop", True))
        watch_interval_s = float(dev_cfg.get("watch_interval_s", 1.0))

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
                    "output_path": output_path,
                    "interval_s": interval_s,
                    "watch_interval_s": watch_interval_s,
                    "loop": loop,
                },
            )
            configured_sensor_ids.add(sensor_id)

            watcher = JetiSpectravalFileWatcher(
                device_id=device_id,
                sensor_id=sensor_id,
                input_path=output_path,
                label=label,
                location=location,
                svc_root=_SVC_DIR,
            )
            clients_with_interval.append((watcher, watch_interval_s))

            if is_development:
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
                    "timeout_s": timeout_s,
                    "float_byte_order": float_byte_order,
                },
            )
            configured_sensor_ids.add(sensor_id)

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

    if is_production and configured_sensor_ids:
        delete_sensor_readings_for_ids(list(configured_sensor_ids))
    prune_sensors_to_ids(list(configured_sensor_ids))
    return clients_with_interval


def _worker_loop(client: SensorClient, interval_s: float) -> None:
    global _stop_flag
    logger.info(f"Sensor worker started for {client} with interval {interval_s}s")
    while not _stop_flag:
        try:
            readings: List[SensorReading] = list(client.poll())
        except Exception as e:
            logger.exception("Sensor worker poll failed for %s: %s", client, e)
            _set_sensor_error(str(getattr(client, "id", client)), e)
            readings = []
        else:
            _clear_sensor_error(str(getattr(client, "id", client)))
        if readings:
            logger.debug(f"Manager: received {len(readings)} readings from {client}")
        for r in readings:
            if r.metric == "spectrum" and r.spectrum is not None:
                insert_sensor_spectrum(r.sensor_id, r.ts, r.spectrum)
            else:
                insert_sensor_reading(r.sensor_id, r.ts, r.metric, r.value)
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
