"""Seed one simulated month of sensor readings and time the sensor queries.

Used as evidence for RFC-0006. Volumes follow
``svc/config/production.example/sensors_config.json``: two T-10A bodies with
eight heads each at 60 s, one JETI at 60 s (21 stored metrics), and one EKO
C-BOX at 5 s (11 metrics). Spectra are not seeded.

Usage, from ``svc``::

    uv run python scripts/bench_sensor_month.py <empty-scratch-dir>

The scratch directory becomes ``SVC_DATA_DIR``; never point it at real data.
"""
from __future__ import annotations

import os
import sqlite3
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

DAYS = 30
START_TS = 1_780_000_000.0
EKO_METRICS = [
    "board_temp_c", "ghi_w_m2", "dni_w_m2", "sensor_temp_c", "dhi_w_m2",
    "latitude_deg", "longitude_deg", "sun_elevation_deg", "sun_azimuth_deg",
    "gps_timestamp_s", "gps_satellites",
]
JETI_METRICS = [f"jeti_metric_{i:02d}" for i in range(21)]


def _timings_ms(fn: Callable[[], object], runs: int) -> tuple[float, float]:
    """Return the median and p95 run time of ``fn`` in milliseconds."""
    times = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000)
    times.sort()
    return statistics.median(times), times[int(0.95 * (runs - 1))]


def main(data_dir: str) -> None:
    os.environ["SVC_ENVIRONMENT"] = "development"
    os.environ["SVC_DATA_DIR"] = data_dir
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from app import state
    from app.models import SensorIngestEvent

    if os.path.exists(state.AUDIT_DB_FILE):
        raise SystemExit(f"{state.AUDIT_DB_FILE} exists; use an empty directory")

    sensors = [
        (f"KM{body}-H{head}", "t10a", ["lux"], 60.0)
        for body in (1, 2)
        for head in range(1, 9)
    ]
    sensors.append(("JETI-SB-1", "jeti_spectraval", JETI_METRICS, 60.0))
    sensors.append(("EKO-CBOX-01", "eko_ms90_plus", EKO_METRICS, 5.0))

    state._ensure_sensor_db()
    for sensor_id, kind, _, _ in sensors:
        state.register_sensor(sensor_id, kind, sensor_id, None, {})

    total = 0
    started = time.perf_counter()
    with sqlite3.connect(state.AUDIT_DB_FILE) as conn:
        for sensor_id, _, metrics, interval_s in sensors:
            count = int(DAYS * 86400 / interval_s)
            rows = (
                (sensor_id, START_TS + i * interval_s, metric, 1.0)
                for i in range(count)
                for metric in metrics
            )
            conn.executemany(
                "INSERT INTO sensor_readings (sensor_id, ts, metric, value) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            total += count * len(metrics)
    seed_s = time.perf_counter() - started
    size_mb = os.path.getsize(state.AUDIT_DB_FILE) / 1e6
    print(f"rows={total} seed_s={seed_s:.1f} db_mb={size_mb:.0f}")

    end_ts = START_TS + DAYS * 86400
    median, p95 = _timings_ms(state.fetch_latest_readings, 10)
    print(f"fetch_latest_readings ms median={median:.0f} p95={p95:.0f}")
    median, p95 = _timings_ms(
        lambda: state.fetch_readings(
            "EKO-CBOX-01", "ghi_w_m2", end_ts - 86400, end_ts
        ),
        10,
    )
    print(f"fetch_readings one day ms median={median:.0f} p95={p95:.0f}")

    batches = [0]

    def ingest_batch() -> None:
        batches[0] += 1
        base_ts = end_ts + batches[0] * 10_000
        events = [
            SensorIngestEvent(
                event_id=str(uuid.uuid4()),
                sensor_id="EKO-CBOX-01",
                observed_ts=base_ts + i * 5.0,
                metrics={metric: 1.0 for metric in EKO_METRICS},
            )
            for i in range(1000)
        ]
        state.ingest_sensor_events(events)

    median, p95 = _timings_ms(ingest_batch, 10)
    print(f"ingest 1000-event batch ms median={median:.0f} p95={p95:.0f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
