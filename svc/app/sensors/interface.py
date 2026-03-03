# app/sensors/interface.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Iterable


@dataclass
class SensorReading:
    sensor_id: str      # e.g. "KM1-00"
    metric: str         # e.g. "lux"
    value: float
    ts: float           # unix timestamp


class SensorClient(Protocol):
    """
    Minimal interface all sensor drivers must implement.
    One instance typically represents one physical device (which may have multiple heads).
    """

    id: str  # device id, e.g. "KM1"

    def poll(self) -> Iterable[SensorReading]:
        """
        Poll the device once and return zero or more readings.

        For T-10A this might return one reading per head:
          KM1-00 lux, KM1-01 lux, ...

        For JETI this might return multiple metrics from the spectrum for a single sensor.
        """
        ...
