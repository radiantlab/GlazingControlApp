from __future__ import annotations
import logging
import os
import time
from datetime import datetime
from typing import Iterable, List, Tuple
from .interface import SensorClient, SensorReading
from .spectral_metrics import compute_jeti_metrics

logger = logging.getLogger(__name__)

_IDX_DATE = 1
_IDX_TIME = 2
_IDX_LUX = 5
_IDX_SPECTRAL_START = 8


def _parse_cap_row(line: str) -> Tuple[float, List[str]]:
    """Parse one .cap line. Returns (lux_value, spectral-value strings)."""
    parts = [p.strip() for p in line.split(";")]
    if len(parts) < _IDX_SPECTRAL_START + 1:
        raise ValueError(f"Row has too few fields: {len(parts)}")
    try:
        lux = float(parts[_IDX_LUX])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse lux from row: {e}") from e
    spectral = parts[_IDX_SPECTRAL_START:]
    return lux, spectral


def _parse_cap_timestamp(line: str) -> float | None:
    """Parse measurement timestamp from one .cap line."""
    parts = [p.strip() for p in line.split(";")]
    if len(parts) <= _IDX_TIME:
        return None

    date_str = parts[_IDX_DATE]
    time_str = parts[_IDX_TIME]
    if not date_str or not time_str:
        return None

    try:
        dt = datetime.strptime(
            f"{date_str} {time_str.upper()}",
            "%m/%d/%Y %I:%M:%S%p",
        )
        return dt.timestamp()
    except ValueError:
        return None


class JetiSpectravalFileWatcher(SensorClient):
    """Watches a Jeti Spectraval .cap file for new readings."""

    def __init__(
        self,
        device_id: str,
        sensor_id: str,
        input_path: str,
        label: str,
        location: str | None = None,
        svc_root: str | None = None,
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._label = label
        self._location = location
        self._input_path = input_path
        self._svc_root = svc_root or os.getcwd()

        if os.path.isabs(input_path):
            self._input_abs = input_path
        else:
            self._input_abs = os.path.normpath(os.path.join(self._svc_root, input_path))

        self._path_looks_like_file = self._input_abs.lower().endswith(".cap")
        self._file_pos = 0
        self._last_measurement_ts: float | None = None
        self._is_dir = False
        self._current_file: str | None = None
        self._refresh_source_state(start_at_end=True)

        logger.info(
            "JetiSpectravalFileWatcher watching %s (dir=%s) -> current %s pos %s",
            self._input_abs,
            self._is_dir,
            self._current_file,
            self._file_pos,
        )

    def _get_newest_cap_file(self, folder: str) -> str | None:
        """Find the .cap file with the latest mtime in the folder."""
        try:
            candidates = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.endswith(".cap")
            ]
            if not candidates:
                return None
            return max(candidates, key=os.path.getmtime)
        except Exception as e:
            logger.error(f"Error scanning folder {folder}: {e}")
            return None

    def _set_current_file(self, new_file: str | None, *, start_at_end: bool) -> None:
        if new_file == self._current_file:
            return

        self._current_file = new_file
        self._last_measurement_ts = None
        if new_file and os.path.exists(new_file):
            self._file_pos = os.path.getsize(new_file) if start_at_end else 0
        else:
            self._file_pos = 0

    def _refresh_source_state(self, *, start_at_end: bool) -> None:
        if os.path.isdir(self._input_abs):
            self._is_dir = True
            newest = self._get_newest_cap_file(self._input_abs)
            self._set_current_file(newest, start_at_end=start_at_end)
            return

        if os.path.isfile(self._input_abs):
            self._is_dir = False
            self._set_current_file(self._input_abs, start_at_end=start_at_end)
            return

        self._is_dir = not self._path_looks_like_file
        if self._current_file and not os.path.exists(self._current_file):
            self._set_current_file(None, start_at_end=False)

    def poll(self) -> Iterable[SensorReading]:
        """Check for new lines in the watched file."""
        previous_file = self._current_file
        self._refresh_source_state(start_at_end=False)
        if self._current_file and self._current_file != previous_file:
            logger.info("Watcher: switched to file %s", self._current_file)

        if not self._current_file or not os.path.exists(self._current_file):
            return []

        try:
            current_size = os.path.getsize(self._current_file)
            if current_size < self._file_pos:
                self._file_pos = 0

            if current_size == self._file_pos:
                return []

            logger.debug(f"Watcher: size changed {self._file_pos} -> {current_size}")

            with open(self._current_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._file_pos)
                new_data = f.read()
                self._file_pos = f.tell()

            if not new_data:
                return []

            lines = new_data.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    lux, spectral = _parse_cap_row(line)
                    measurement_ts = _parse_cap_timestamp(line) or time.time()
                    metrics = compute_jeti_metrics(lux=lux, spectral_values=spectral)

                    if self._last_measurement_ts is not None:
                        dt = measurement_ts - self._last_measurement_ts
                        if dt > 0:
                            metrics["sample_interval_s"] = dt
                    self._last_measurement_ts = measurement_ts

                    if not metrics:
                        continue

                    logger.debug(
                        "Watcher: parsed metrics for %s at ts=%s (%d values)",
                        self._sensor_id,
                        measurement_ts,
                        len(metrics),
                    )
                    for metric, value in metrics.items():
                        yield SensorReading(
                            sensor_id=self._sensor_id,
                            metric=metric,
                            value=value,
                            ts=measurement_ts,
                        )
                except ValueError as e:
                    logger.warning(f"Watcher: failed to parse line '{line}': {e}")
                    continue

        except Exception as e:
            logger.error(f"Error reading watcher file {self._current_file}: {e}")
