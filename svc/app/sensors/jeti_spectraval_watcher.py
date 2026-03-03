from __future__ import annotations
import logging
import os
import time
from typing import Iterable, List, Tuple
from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


_IDX_DATE = 1
_IDX_TIME = 2
_IDX_LUX = 5
_IDX_SPECTRAL_START = 8
_DELIM = "; "

def _parse_cap_row(line: str) -> Tuple[float, List[str]]:
    """Parse one .cap line. Returns (lux_value, list of spectral value strings)."""
    parts = [p.strip() for p in line.split(";")]
    if len(parts) < _IDX_SPECTRAL_START + 1:
        raise ValueError(f"Row has too few fields: {len(parts)}")
    try:
        lux = float(parts[_IDX_LUX])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse lux from row: {e}") from e
    spectral = parts[_IDX_SPECTRAL_START:]
    return lux, spectral


class JetiSpectravalFileWatcher(SensorClient):
    """
    Watches a Jeti Spectraval .cap file for new readings.
    """

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
        
        # Resolve paths relative to svc root
        if os.path.isabs(input_path):
             self._input_abs = input_path
        else:
             self._input_abs = os.path.normpath(os.path.join(self._svc_root, input_path))

        self._file_pos = 0
        
        # Initial seek to end if file exists (or start from beginning? 
        # Usually for a "live" system we might want only new data, 
        # but for simplicity let's start from 0 if it's not too huge, 
        # or seek to end. Let's seek to end to avoid re-ingesting old history for now).
        if os.path.exists(self._input_abs):
            if os.path.isdir(self._input_abs):
                self._is_dir = True
                self._current_file = self._get_newest_cap_file(self._input_abs)
            else:
                self._is_dir = False
                self._current_file = self._input_abs
        else:
            # Path doesn't exist yet, assume file for now or wait
            self._is_dir = False
            self._current_file = None

        if self._current_file and os.path.exists(self._current_file):
            self._file_pos = os.path.getsize(self._current_file)
        
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

    def poll(self) -> Iterable[SensorReading]:
        """
        Check for new lines in the watched file.
        """
        # If directory mode, check for file rotation
        if self._is_dir:
            newest = self._get_newest_cap_file(self._input_abs)
            if newest and newest != self._current_file:
                logger.info(f"Watcher: switching to new file {newest}")
                self._current_file = newest
                self._file_pos = 0  # START FROM BEGINNING for new files
        
        if not self._current_file or not os.path.exists(self._current_file):
            return

        try:
            current_size = os.path.getsize(self._current_file)
            if current_size < self._file_pos:
                # File was truncated or rotated
                self._file_pos = 0
            
            if current_size == self._file_pos:
                return

            logger.debug(f"Watcher: size changed {self._file_pos} -> {current_size}")

            with open(self._current_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._file_pos)
                new_data = f.read()
                self._file_pos = f.tell()

            if not new_data:
                return

             # Process lines
            lines = new_data.split("\n")
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Skip header if it appears (e.g. from file rotation or initial read)
                # if line.startswith("Date and Time"):
                #     continue
                
                try:
                    lux, _ = _parse_cap_row(line)
                    logger.debug(f"Watcher: parsed lux={lux}")
                    yield SensorReading(
                        sensor_id=self._sensor_id,
                        metric="lux",
                        value=lux,
                        ts=time.time()
                    )
                except ValueError as e:
                    logger.warning(f"Watcher: failed to parse line '{line}': {e}")
                    continue

        except Exception as e:
            logger.error(f"Error reading watcher file {self._current_file}: {e}")
