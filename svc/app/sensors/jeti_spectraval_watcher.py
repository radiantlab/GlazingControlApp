from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime
from typing import Iterable, List, Tuple
from zoneinfo import ZoneInfo
from .interface import SensorClient, SensorReading
from .spectral_metrics import compute_jeti_metrics, _clean_spectral_values

logger = logging.getLogger(__name__)

_IDX_DATE = 1
_IDX_TIME = 2
_IDX_LUX = 5
_IDX_SPECTRAL_START = 8


def _parse_lival_row(line: str) -> Tuple[float, List[str]]:
    """Parse one semicolon-delimited LiVal capture row."""
    parts = [p.strip() for p in line.split(";")]
    if len(parts) < _IDX_SPECTRAL_START + 1:
        raise ValueError(f"Row has too few fields: {len(parts)}")
    try:
        lux = float(parts[_IDX_LUX])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse lux from row: {e}") from e
    spectral = parts[_IDX_SPECTRAL_START:]
    return lux, spectral


def _parse_lival_timestamp(
    line: str,
    source_timezone: ZoneInfo | None = None,
) -> float | None:
    """Parse the local measurement time recorded in one LiVal capture row."""
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
        if source_timezone is not None:
            dt = dt.replace(tzinfo=source_timezone)
        return dt.timestamp()
    except ValueError:
        return None


class JetiSpectravalFileWatcher(SensorClient):
    """Watches a line-oriented JETI LiVal capture file for new readings."""

    def __init__(
        self,
        device_id: str,
        sensor_id: str,
        input_path: str,
        label: str,
        location: str | None = None,
        svc_root: str | None = None,
        input_kind: str = "auto",
        cursor_dir: str | None = None,
        initial_position: str = "end",
        max_records_per_poll: int = 250,
        max_read_bytes: int = 4 * 1024 * 1024,
        source_timezone: str | None = None,
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

        normalized_input_kind = input_kind.strip().casefold()
        if normalized_input_kind not in {"auto", "file", "directory"}:
            raise ValueError("input_kind must be auto, file, or directory")
        self._input_kind = normalized_input_kind
        normalized_initial_position = initial_position.strip().casefold()
        if normalized_initial_position not in {"beginning", "end"}:
            raise ValueError("initial_position must be beginning or end")
        if max_records_per_poll <= 0:
            raise ValueError("max_records_per_poll must be positive")
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be positive")
        self._initial_position = normalized_initial_position
        self._max_records_per_poll = int(max_records_per_poll)
        self._max_read_bytes = int(max_read_bytes)
        self._source_timezone = ZoneInfo(source_timezone) if source_timezone else None
        self._path_looks_like_file = (
            normalized_input_kind == "file"
            or (
                normalized_input_kind == "auto"
                and (
                    self._input_abs.lower().endswith(".cap")
                    or os.path.isfile(self._input_abs)
                )
            )
        )
        safe_sensor_id = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in sensor_id
        )
        if cursor_dir:
            self._cursor_path = os.path.join(
                os.path.abspath(cursor_dir),
                f"{safe_sensor_id}.glazing-cursor.json",
            )
        else:
            self._cursor_path = (
                f"{self._input_abs}.{safe_sensor_id}.glazing-cursor.json"
                if self._path_looks_like_file
                else os.path.join(
                    self._input_abs,
                    f".{safe_sensor_id}.glazing-cursor.json",
                )
            )
        self._file_pos = 0
        self._pending_file_pos: int | None = None
        self._pending_file: str | None = None
        self._pending_last_measurement_ts: float | None = None
        self._last_measurement_ts: float | None = None
        self._is_dir = False
        self._current_file: str | None = None
        self.last_error: str | None = None
        self._refresh_source_state(
            start_at_end=self._initial_position == "end"
        )
        if not self._load_cursor() and self._current_file:
            # Persist the enrollment baseline immediately. If the process stops
            # before the next row arrives, a restart can still ingest rows that
            # were appended during the downtime.
            self._persist_cursor()

        logger.info(
            "JetiSpectravalFileWatcher watching %s (dir=%s) -> current %s pos %s",
            self._input_abs,
            self._is_dir,
            self._current_file,
            self._file_pos,
        )

    def _get_newest_capture_file(self, folder: str) -> str | None:
        """Find the newest supported LiVal capture-text file in a folder."""
        try:
            candidates = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith((".cap", ".txt", ".xlsx"))
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
        if self._input_kind == "file":
            self._is_dir = False
            current = self._input_abs if os.path.isfile(self._input_abs) else None
            self._set_current_file(current, start_at_end=start_at_end)
            return

        if self._input_kind == "directory":
            self._is_dir = True
            newest = (
                self._get_newest_capture_file(self._input_abs)
                if os.path.isdir(self._input_abs)
                else None
            )
            self._set_current_file(newest, start_at_end=start_at_end)
            return

        if os.path.isdir(self._input_abs):
            self._is_dir = True
            newest = self._get_newest_capture_file(self._input_abs)
            self._set_current_file(newest, start_at_end=start_at_end)
            return

        if os.path.isfile(self._input_abs):
            self._is_dir = False
            self._set_current_file(self._input_abs, start_at_end=start_at_end)
            return

        self._is_dir = not self._path_looks_like_file
        if self._current_file and not os.path.exists(self._current_file):
            self._set_current_file(None, start_at_end=False)

    def _load_cursor(self) -> bool:
        """Resume a previously acknowledged byte offset for this exact file."""
        if not self._current_file or not os.path.isfile(self._cursor_path):
            return False
        try:
            with open(self._cursor_path, "r", encoding="utf-8") as cursor_file:
                payload = json.load(cursor_file)
            cursor_file_path = os.path.normcase(
                os.path.abspath(str(payload.get("file", "")))
            )
            current_file_path = os.path.normcase(os.path.abspath(self._current_file))
            position = int(payload.get("position", -1))
            current_size = os.path.getsize(self._current_file)
            if cursor_file_path == current_file_path and 0 <= position <= current_size:
                self._file_pos = position
                raw_last_ts = payload.get("last_measurement_ts")
                self._last_measurement_ts = (
                    float(raw_last_ts) if raw_last_ts is not None else None
                )
                logger.info(
                    "JetiSpectravalFileWatcher resumed %s at byte %d",
                    self._current_file,
                    self._file_pos,
                )
                return True
        except Exception as exc:
            logger.warning("Ignoring invalid JETI cursor %s: %s", self._cursor_path, exc)
        return False

    def _persist_cursor(self) -> None:
        if not self._current_file:
            return
        parent = os.path.dirname(self._cursor_path)
        os.makedirs(parent, exist_ok=True)
        temporary = f"{self._cursor_path}.partial-{os.getpid()}"
        payload = {
            "version": 1,
            "file": os.path.abspath(self._current_file),
            "position": self._file_pos,
            "last_measurement_ts": self._last_measurement_ts,
            "updated_at": time.time(),
        }
        try:
            with open(temporary, "w", encoding="utf-8") as cursor_file:
                json.dump(payload, cursor_file)
                cursor_file.flush()
                os.fsync(cursor_file.fileno())
            os.replace(temporary, self._cursor_path)
        except Exception as exc:
            logger.warning("Could not persist JETI cursor %s: %s", self._cursor_path, exc)
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

    @property
    def has_pending_batch(self) -> bool:
        return self._pending_file_pos is not None

    def acknowledge(self) -> None:
        """Commit the pending byte range after its observations are durable."""
        if self._pending_file_pos is None:
            return
        if self._pending_file != self._current_file:
            raise RuntimeError("LiVal source changed before its batch was acknowledged")
        self._file_pos = self._pending_file_pos
        self._last_measurement_ts = self._pending_last_measurement_ts
        self._pending_file_pos = None
        self._pending_file = None
        self._pending_last_measurement_ts = None
        self._persist_cursor()

    def reject(self) -> None:
        """Discard a pending byte range so the next poll retries it."""
        self._pending_file_pos = None
        self._pending_file = None
        self._pending_last_measurement_ts = None

    def poll(self) -> Iterable[SensorReading]:
        """Read one bounded, complete-record batch from the LiVal capture."""
        if self.has_pending_batch:
            raise RuntimeError(
                "The previous LiVal batch must be acknowledged or rejected"
            )
        previous_file = self._current_file
        self._refresh_source_state(start_at_end=False)
        if self._current_file and self._current_file != previous_file:
            logger.info("Watcher: switched to file %s", self._current_file)

        if not self._current_file or not os.path.exists(self._current_file):
            # File producers commonly create the path shortly after startup.
            # The manager's freshness deadline will mark it stale if it does
            # not appear, without causing a false startup failure.
            self.last_error = None
            return []

        try:
            current_size = os.path.getsize(self._current_file)
            if current_size < self._file_pos:
                self._file_pos = 0
                self._last_measurement_ts = None

            if current_size == self._file_pos:
                self.last_error = None
                return []

            logger.debug(f"Watcher: size changed {self._file_pos} -> {current_size}")

            with open(self._current_file, "rb") as source_file:
                source_file.seek(self._file_pos)
                new_bytes = source_file.read(self._max_read_bytes)

            if not new_bytes:
                self.last_error = None
                return []

            complete_chunks: list[bytes] = []
            complete_end = 0
            for chunk in new_bytes.splitlines(keepends=True):
                if not chunk.endswith((b"\n", b"\r")):
                    break
                complete_chunks.append(chunk)
                complete_end += len(chunk)
                if len(complete_chunks) >= self._max_records_per_poll:
                    break
            if not complete_chunks:
                self.last_error = None
                return []

            complete_data = b"".join(complete_chunks).decode(
                "utf-8", errors="replace"
            )
            lines = complete_data.splitlines()
            readings: list[SensorReading] = []
            latest_measurement_ts = self._last_measurement_ts
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    lux, spectral = _parse_lival_row(line)
                    measurement_ts = (
                        _parse_lival_timestamp(line, self._source_timezone)
                        or time.time()
                    )
                    metrics = compute_jeti_metrics(lux=lux, spectral_values=spectral)

                    if latest_measurement_ts is not None:
                        dt = measurement_ts - latest_measurement_ts
                        if dt > 0:
                            metrics["sample_interval_s"] = dt
                    latest_measurement_ts = measurement_ts

                    # Clean raw spectral strings and yield a spectrum reading
                    cleaned_spec = _clean_spectral_values(spectral)
                    if cleaned_spec:
                        readings.append(SensorReading(
                            sensor_id=self._sensor_id,
                            metric="spectrum",
                            value=0.0,
                            ts=measurement_ts,
                            spectrum=cleaned_spec,
                        ))

                    if not metrics:
                        continue

                    logger.debug(
                        "Watcher: parsed metrics for %s at ts=%s (%d values)",
                        self._sensor_id,
                        measurement_ts,
                        len(metrics),
                    )
                    for metric, value in metrics.items():
                        readings.append(SensorReading(
                            sensor_id=self._sensor_id,
                            metric=metric,
                            value=value,
                            ts=measurement_ts,
                        ))
                except ValueError as e:
                    logger.warning(f"Watcher: failed to parse line '{line}': {e}")
                    continue
            self._pending_file = self._current_file
            self._pending_file_pos = self._file_pos + complete_end
            self._pending_last_measurement_ts = latest_measurement_ts
            self.last_error = None
            return readings

        except Exception as e:
            logger.error(f"Error reading watcher file {self._current_file}: {e}")
            self.last_error = str(e)
            self.reject()
            raise


# Compatibility aliases for callers that imported the old implementation names.
_parse_cap_row = _parse_lival_row
_parse_cap_timestamp = _parse_lival_timestamp
