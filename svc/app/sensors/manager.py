# app/sensors/manager.py
from __future__ import annotations
import json
import os
import threading
import time
import logging
from typing import List

from .interface import SensorClient, SensorReading
from .t10a_client import T10AClient, T10AHeadConfig
from app.state import register_sensor, insert_sensor_reading

logger = logging.getLogger(__name__)

# Path to sensor config file; override via env if you want
_SVC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENSORS_CONFIG_FILE = os.getenv(
    "SENSORS_CONFIG_FILE",
    os.path.join(_SVC_DIR, "data", "sensors_config.json")
)

_workers: list[threading.Thread] = []
_clients: list[SensorClient] = []
_stop_flag = False


def _load_config() -> dict:
    """
    Expected JSON structure:

    {
      "t10a": [
        {
          "device_id": "KM1",
          "port": "COM3",
          "interval_s": 60,
          "heads": [
            {"head_no": 0, "sensor_id": "KM1-00", "label": "Desk center"},
            {"head_no": 1, "sensor_id": "KM1-01", "label": "Desk left"}
          ]
        },
        {
          "device_id": "KM2",
          "port": "COM4",
          "interval_s": 60,
          "heads": [
            {"head_no": 0, "sensor_id": "KM2-00", "label": "Window center"}
          ]
        }
      ]
    }
    """
    if not os.path.exists(SENSORS_CONFIG_FILE):
        logger.warning(f"No sensors_config.json found at {SENSORS_CONFIG_FILE}")
        return {"t10a": []}

    with open(SENSORS_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_clients_from_config() -> list[tuple[SensorClient, float]]:
    cfg = _load_config()
    clients_with_interval: list[tuple[SensorClient, float]] = []

    # --- T-10A -------------------------------------------------------------
    for dev_cfg in cfg.get("t10a", [])[:4]:  # enforce 1-4 devices
        device_id = dev_cfg["device_id"]
        port = dev_cfg["port"]
        interval_s = float(dev_cfg.get("interval_s", 60.0))

        heads_cfg: list[T10AHeadConfig] = []
        for h in dev_cfg.get("heads", []):
            hc = T10AHeadConfig(
                head_no=h["head_no"],
                sensor_id=h["sensor_id"],
                label=h.get("label", h["sensor_id"]),
                location=h.get("location"),
            )
            heads_cfg.append(hc)

            # register this sensor in DB so UI can show it
            register_sensor(
                sensor_id=hc.sensor_id,
                kind="t10a",
                label=hc.label,
                location=hc.location,
                config={
                    "device_id": device_id,
                    "port": port,
                    "head_no": hc.head_no,
                },
            )

        if not heads_cfg:
            continue

        client = T10AClient(device_id=device_id, port=port, heads=heads_cfg)
        clients_with_interval.append((client, interval_s))

    return clients_with_interval


def _worker_loop(client: SensorClient, interval_s: float) -> None:
    global _stop_flag
    logger.info(f"Sensor worker started for {client} with interval {interval_s}s")
    while not _stop_flag:
        readings: List[SensorReading] = list(client.poll())
        for r in readings:
            insert_sensor_reading(r.sensor_id, r.ts, r.metric, r.value)
        time.sleep(interval_s)


def start_sensor_workers() -> None:
    """
    Called once at app startup.
    Creates up to 4 clients from config and starts one worker thread per client.
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
