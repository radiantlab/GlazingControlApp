from __future__ import annotations

import logging
import math
import random
import time
from typing import Iterable

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


class EkoMs90PlusSimClient(SensorClient):
    """
    Simulated EKO MS-90+ telemetry source.

    Emits the same key metrics as the real C-BOX integration so dashboards and
    logs behave the same in sim and real modes.
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        latitude_deg: float = 44.5646,
        longitude_deg: float = -123.2620,
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._lat = float(latitude_deg)
        self._lon = float(longitude_deg)
        self._rng = random.Random(f"eko-sim-{device_id}-{sensor_id}")
        self._phase = self._rng.uniform(0.0, math.pi * 2.0)

    @staticmethod
    def _sun_curve(ts: float) -> float:
        seconds_in_day = 24 * 60 * 60
        day_pos = (ts % seconds_in_day) / seconds_in_day
        return max(0.0, math.sin((day_pos - 0.25) * math.pi))

    def poll(self) -> Iterable[SensorReading]:
        now = time.time()
        sun = self._sun_curve(now)
        azimuth = ((now / 240.0) % 360.0 + 90.0) % 360.0
        elevation = max(0.0, sun * 75.0)

        ghi = max(0.0, (sun * 900.0) + self._rng.uniform(-20.0, 20.0))
        dni = max(0.0, (sun * 860.0) + self._rng.uniform(-30.0, 30.0))
        dhi = max(0.0, (sun * 210.0) + self._rng.uniform(-12.0, 12.0))

        board_temp = 19.0 + (sun * 15.0) + 1.2 * math.sin((now / 180.0) + self._phase)
        sensor_temp = board_temp + self._rng.uniform(-1.0, 1.0)
        gps_sats = max(4.0, min(16.0, 11.0 + self._rng.uniform(-2.0, 2.0)))

        metrics = {
            "board_temp_c": board_temp,
            "sensor_temp_c": sensor_temp,
            "ghi_w_m2": ghi,
            "dni_w_m2": dni,
            "dhi_w_m2": dhi,
            "latitude_deg": self._lat,
            "longitude_deg": self._lon,
            "sun_elevation_deg": elevation,
            "sun_azimuth_deg": azimuth,
            "gps_timestamp_s": now,
            "gps_satellites": gps_sats,
        }

        out: list[SensorReading] = []
        for metric, value in metrics.items():
            out.append(
                SensorReading(
                    sensor_id=self._sensor_id,
                    metric=metric,
                    value=float(round(value, 4)),
                    ts=now,
                )
            )
        return out
