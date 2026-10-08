from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable

from app.models import SensorIngestEvent

from .interface import SensorReading


class InvalidSensorObservation(ValueError):
    """Raised when a sensor poll cannot be represented as a durable event."""


def readings_to_ingest_events(
    readings: Iterable[SensorReading],
    *,
    event_namespace: str,
    source: str,
    spectrum_wavelength_start: int = 380,
    spectrum_wavelength_step: int = 1,
) -> list[SensorIngestEvent]:
    """Combine scalar and spectral readings into retry-safe observation events."""
    grouped: dict[tuple[str, float], dict[str, object]] = {}
    for reading in readings:
        timestamp = float(reading.ts)
        value = float(reading.value)
        if (
            not math.isfinite(timestamp)
            or timestamp <= 0
            or not math.isfinite(value)
        ):
            raise InvalidSensorObservation(
                f"Non-finite reading from {source}: "
                f"{reading.sensor_id}/{reading.metric}"
            )

        key = (str(reading.sensor_id), timestamp)
        event = grouped.setdefault(
            key,
            {
                "sensor_id": str(reading.sensor_id),
                "observed_ts": timestamp,
                "metrics": {},
                "source": source[:256],
            },
        )
        if reading.metric == "spectrum" and reading.spectrum is not None:
            spectrum = [float(item) for item in reading.spectrum]
            if not spectrum or any(not math.isfinite(item) for item in spectrum):
                raise InvalidSensorObservation(
                    f"Invalid spectrum from {source}: {reading.sensor_id}"
                )
            event["spectrum"] = spectrum
            event["spectrum_wavelength_start"] = spectrum_wavelength_start
            event["spectrum_wavelength_step"] = spectrum_wavelength_step
        else:
            metrics = event["metrics"]
            assert isinstance(metrics, dict)
            metrics[str(reading.metric)] = value

    events: list[SensorIngestEvent] = []
    safe_namespace = "".join(
        char if char.isalnum() or char in "_.:-" else "-"
        for char in event_namespace
    )[:48]
    for event in grouped.values():
        if not event["metrics"]:
            raise InvalidSensorObservation(
                f"Spectrum-only observation is unsupported: {event['sensor_id']}"
            )
        identity_json = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()
        events.append(
            SensorIngestEvent(
                event_id=f"{safe_namespace}:{digest}"[:128],
                **event,
            )
        )

    return sorted(
        events,
        key=lambda item: (float(item.observed_ts), str(item.sensor_id)),
    )
