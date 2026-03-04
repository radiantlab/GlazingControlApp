# app/sensors/manager.py
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import List

from app.config import MODE
from app.state import insert_sensor_reading, prune_sensors_to_ids, register_sensor

from .eko_cbox_modbus_client import EkoCBoxModbusClient
from .eko_ms90_plus_sim_client import EkoMs90PlusSimClient
from .interface import SensorClient, SensorReading
from .jeti_specfirm_client import JetiSpecfirmClient
from .jeti_spectraval_sim import JetiSpectravalSimClient
from .jeti_spectraval_watcher import JetiSpectravalFileWatcher
from .t10a_client import T10AClient, T10AHeadConfig
from .t10a_sim_client import T10ASimClient

logger = logging.getLogger(__name__)

# Path to sensor config file; override via env if desired.
# __file__ is app/sensors/manager.py -> need svc root (parent of app)
_SVC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SENSORS_CONFIG_FILE = os.getenv(
    "SENSORS_CONFIG_FILE",
    os.path.join(_SVC_DIR, "data", "sensors_config.json"),
)

_workers: list[threading.Thread] = []
_clients: list[SensorClient] = []
_stop_flag = False


def _load_config() -> dict:
    """
    Expected JSON structure (keys optional):

    {
      "t10a": [ ... ],
      "jeti_spectraval": [ ... ],
      "eko_ms90_plus": [ ... ]
    }
    """
    if not os.path.exists(SENSORS_CONFIG_FILE):
        logger.warning(f"No sensors_config.json found at {SENSORS_CONFIG_FILE}")
        return {"t10a": [], "jeti_spectraval": [], "eko_ms90_plus": []}

    with open(SENSORS_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_clients_from_config() -> list[tuple[SensorClient, float]]:
    cfg = _load_config()
    clients_with_interval: list[tuple[SensorClient, float]] = []
    configured_sensor_ids: set[str] = set()

    enable_t10a_in_sim = os.getenv("SVC_ENABLE_T10A_IN_SIM", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    enable_jeti_serial_in_sim = os.getenv(
        "SVC_ENABLE_JETI_SERIAL_IN_SIM", "false"
    ).lower() in {"1", "true", "yes", "on"}
    enable_eko_in_sim = os.getenv("SVC_ENABLE_EKO_IN_SIM", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # --- T-10A -------------------------------------------------------------
    t10a_configs = cfg.get("t10a", [])[:4]  # enforce 1-4 devices
    use_real_t10a = MODE != "sim" or enable_t10a_in_sim
    if MODE == "sim" and not enable_t10a_in_sim and t10a_configs:
        logger.info(
            "SVC_MODE=sim: using simulated T10A data for %d config(s). "
            "Set SVC_ENABLE_T10A_IN_SIM=true to poll real serial devices in sim mode.",
            len(t10a_configs),
        )

    for dev_cfg in t10a_configs:
        device_id = dev_cfg["device_id"]
        port = str(dev_cfg.get("port", "SIM"))
        interval_s = float(dev_cfg.get("interval_s", 60.0))
        timeout_s = float(dev_cfg.get("timeout_s", 1.0))
        protocol_cfg = dev_cfg.get("protocol", {})

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
                    "port": port,
                    "head_no": hc.head_no,
                    "timeout_s": timeout_s,
                    "protocol": protocol_cfg,
                },
            )
            configured_sensor_ids.add(hc.sensor_id)

        if not heads_cfg:
            continue

        if use_real_t10a:
            try:
                client = T10AClient(
                    device_id=device_id,
                    port=port,
                    heads=heads_cfg,
                    timeout_s=timeout_s,
                    protocol=protocol_cfg,
                )
                clients_with_interval.append((client, interval_s))
            except Exception as e:
                logger.warning("Skip T10A device %s (port %s): %s", device_id, port, e)
        else:
            clients_with_interval.append(
                (
                    T10ASimClient(
                        device_id=device_id,
                        heads=heads_cfg,
                    ),
                    interval_s,
                )
            )

    # --- JETI spectraval ---------------------------------------------------
    # Supported transports:
    #   - file (default): watcher of .cap output path, optional simulator writer in sim mode
    #   - serial_scpi: direct SPECFIRM serial polling
    for dev_cfg in cfg.get("jeti_spectraval", [])[:4]:
        sensor_id = dev_cfg.get("sensor_id", "JETI-00")
        device_id = dev_cfg.get("device_id", "JETI")
        interval_s = float(dev_cfg.get("interval_s", 60.0))
        label = dev_cfg.get("label", sensor_id)
        location = dev_cfg.get("location")

        transport = str(dev_cfg.get("transport", "file")).lower()
        if transport in {"serial_scpi", "serial", "specfirm"}:
            if MODE == "sim" and not enable_jeti_serial_in_sim:
                logger.info(
                    "SVC_MODE=sim: skipping JETI serial_scpi config for %s. "
                    "Set SVC_ENABLE_JETI_SERIAL_IN_SIM=true to enable it.",
                    sensor_id,
                )
                continue

            port = dev_cfg.get("port")
            if not port:
                logger.warning("Skip JETI serial_scpi %s: missing 'port'", sensor_id)
                continue

            baudrate = int(dev_cfg.get("baudrate", 921600))
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

            continue

        # Default/file watcher transport.
        template_path = dev_cfg.get("template_path", "")
        output_path = dev_cfg.get("output_path")
        if not output_path:
            logger.warning("Skip Jeti Spectraval %s: missing 'output_path'", sensor_id)
            continue

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

            if MODE == "sim":
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

    # --- EKO MS-90+ (via C-BOX Modbus RTU) -------------------------------
    eko_configs = cfg.get("eko_ms90_plus", [])[:4]
    use_real_eko = MODE != "sim" or enable_eko_in_sim
    if MODE == "sim" and not enable_eko_in_sim and eko_configs:
        logger.info(
            "SVC_MODE=sim: using simulated EKO MS-90+ data for %d config(s). "
            "Set SVC_ENABLE_EKO_IN_SIM=true to poll real serial devices in sim mode.",
            len(eko_configs),
        )

    for dev_cfg in eko_configs:
        sensor_id = dev_cfg.get("sensor_id", "EKO-00")
        device_id = dev_cfg.get("device_id", "EKO-CBOX")
        port = dev_cfg.get("port") or "SIM"
        if use_real_eko and (not port or port == "SIM"):
            logger.warning("Skip EKO MS-90+ %s: missing 'port'", sensor_id)
            continue

        label = dev_cfg.get("label", sensor_id)
        location = dev_cfg.get("location")
        interval_s = float(dev_cfg.get("interval_s", 5.0))
        baudrate = int(dev_cfg.get("baudrate", 9600))
        slave_address = int(dev_cfg.get("slave_address", 1))
        timeout_s = float(dev_cfg.get("timeout_s", 1.0))
        float_byte_order = str(dev_cfg.get("float_byte_order", "ABCD"))

        try:
            register_sensor(
                sensor_id=sensor_id,
                kind="eko_ms90_plus",
                label=label,
                location=location,
                config={
                    "device_id": device_id,
                    "port": port,
                    "baudrate": baudrate,
                    "slave_address": slave_address,
                    "timeout_s": timeout_s,
                    "float_byte_order": float_byte_order,
                },
            )
            configured_sensor_ids.add(sensor_id)

            if use_real_eko:
                eko_client = EkoCBoxModbusClient(
                    device_id=device_id,
                    sensor_id=sensor_id,
                    port=port,
                    slave_address=slave_address,
                    baudrate=baudrate,
                    timeout_s=timeout_s,
                    label=label,
                    location=location,
                    float_byte_order=float_byte_order,
                )
                clients_with_interval.append((eko_client, interval_s))
            else:
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
        except Exception as e:
            logger.warning("Skip EKO MS-90+ %s: %s", sensor_id, e)

    prune_sensors_to_ids(list(configured_sensor_ids))
    return clients_with_interval


def _worker_loop(client: SensorClient, interval_s: float) -> None:
    global _stop_flag
    logger.info(f"Sensor worker started for {client} with interval {interval_s}s")
    while not _stop_flag:
        readings: List[SensorReading] = list(client.poll())
        if readings:
            logger.debug(f"Manager: received {len(readings)} readings from {client}")
        for r in readings:
            insert_sensor_reading(r.sensor_id, r.ts, r.metric, r.value)
        time.sleep(interval_s)


def start_sensor_workers() -> None:
    """
    Called once at app startup.
    Creates clients from config and starts one worker thread per client.
    """
    global _workers, _clients, _stop_flag
    _stop_flag = False

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
    global _stop_flag
    _stop_flag = True
