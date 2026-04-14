from __future__ import annotations

import logging
import math
import random
import time
from typing import Iterable

from .interface import SensorClient, SensorReading
from .t10a_client import T10AHeadConfig

logger = logging.getLogger(__name__)


class T10ASimClient(SensorClient):
    """
    Simulated T-10A body with one or more heads.

    Produces one lux reading per configured head with a smooth daytime profile
    plus small jitter so live graphs look realistic.
    """

    def __init__(
        self,
        *,
        device_id: str,
        heads: list[T10AHeadConfig],
    ) -> None:
        self.id = device_id
        self._heads = list(heads)
        self._rng = random.Random(f"t10a-sim-{device_id}")
        self._phase = self._rng.uniform(0.0, math.pi * 2.0)

    @staticmethod
    def _daylight_factor(ts: float) -> float:
        seconds_in_day = 24 * 60 * 60
        day_pos = (ts % seconds_in_day) / seconds_in_day  # 0.0..1.0
        # Shift so peak is around solar noon.
        return max(0.0, math.sin((day_pos - 0.25) * math.pi))

    def poll(self) -> Iterable[SensorReading]:
        now = time.time()
        daylight = self._daylight_factor(now)

        out: list[SensorReading] = []
        for idx, head in enumerate(self._heads):
            base_lux = 40.0 + (idx * 25.0)
            daytime_lux = 620.0 * daylight
            wave = 22.0 * math.sin((now / 45.0) + self._phase + idx)
            jitter = self._rng.uniform(-6.0, 6.0)
            value = max(0.0, base_lux + daytime_lux + wave + jitter)

            out.append(
                SensorReading(
                    sensor_id=head.sensor_id,
                    metric="lux",
                    value=float(round(value, 3)),
                    ts=now,
                )
            )
        return out
