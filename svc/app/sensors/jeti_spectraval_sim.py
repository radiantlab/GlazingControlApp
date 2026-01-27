# app/sensors/jeti_spectraval_sim.py
"""
Jeti Spectraval sensor simulator

Emulates the Jeti Spectraval by:
1. Writing .cap files in the same format as the real sensor (production-like output).
2. Feeding the existing sensor API via SensorReading so /metrics/latest and /metrics/history
   show the data without a separate .cap reader.

Template .cap format: semicolon-delimited lines;
  "Date and Time:; <date>; <time>; ; Ev [lx] (CIE1931 2°); <lux>; ; Spectral Values (380 nm - 1000 nm); <v380>; ..."
"""
from __future__ import annotations
import logging
import os
import time
from datetime import datetime
from typing import Iterable, List, Tuple

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)

# Column indices in .cap row (after split by ";")
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


def load_template_rows(template_path: str, encoding: str = "latin-1") -> Tuple[List[str], List[Tuple[float, List[str]]]]:
    """
    Load template .cap file. Returns (header_parts_from_first_line, [(lux, spectral_strs), ...]).
    header_parts is the full list of field strings for the first line so we can reuse labels.
    """
    if not os.path.isabs(template_path):
        # Assume relative to cwd; caller typically passes path relative to svc root
        pass
    with open(template_path, "r", encoding=encoding) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    if not lines:
        raise ValueError(f"Template file is empty: {template_path}")
    header_parts = [p.strip() for p in lines[0].split(";")]
    rows: List[Tuple[float, List[str]]] = []
    for i, line in enumerate(lines):
        try:
            lux, spectral = _parse_cap_row(line)
            rows.append((lux, spectral))
        except ValueError as e:
            logger.warning("Skip template line %s: %s", i + 1, e)
    if not rows:
        raise ValueError(f"No valid data rows in template: {template_path}")
    return header_parts, rows


def build_cap_line(header_parts: List[str], date_str: str, time_str: str, lux: float, spectral: List[str]) -> str:
    """Build one .cap line reusing header labels and supplying date, time, lux, spectral values."""
    out = list(header_parts)
    out[_IDX_DATE] = date_str
    out[_IDX_TIME] = time_str
    out[_IDX_LUX] = str(lux)
    n = min(len(spectral), len(out) - _IDX_SPECTRAL_START)
    out[_IDX_SPECTRAL_START : _IDX_SPECTRAL_START + n] = spectral[:n]
    return _DELIM.join(out)


class JetiSpectravalSimClient(SensorClient):
    """
    Simulates the Jeti Spectraval: writes .cap files and yields SensorReading(s) for the API.
    """

    def __init__(
        self,
        device_id: str,
        sensor_id: str,
        template_path: str,
        output_path: str,
        label: str,
        interval_s: float = 60.0,
        loop: bool = True,
        location: str | None = None,
        svc_root: str | None = None,
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._label = label
        self._location = location
        self._output_path = output_path
        self._template_path = template_path
        self._interval_s = interval_s
        self._loop = loop
        self._svc_root = svc_root or os.getcwd()

        # Resolve paths relative to svc root
        def _resolve(p: str) -> str:
            if os.path.isabs(p):
                return p
            return os.path.normpath(os.path.join(self._svc_root, p))

        self._template_abs = _resolve(template_path)
        self._output_abs = _resolve(output_path)

        self._header_parts, self._template_rows = load_template_rows(self._template_abs)
        self._row_index = 0
        self._file_handle = None  # open on first write

        logger.info(
            "JetiSpectravalSimClient device_id=%s sensor_id=%s output=%s template_rows=%s",
            device_id,
            sensor_id,
            self._output_abs,
            len(self._template_rows),
        )

    def _ensure_output_dir(self) -> None:
        d = os.path.dirname(self._output_abs)
        if d:
            os.makedirs(d, exist_ok=True)

    def _write_row(self, lux: float, spectral: List[str], ts: float) -> None:
        now = datetime.utcfromtimestamp(ts)
        date_str = now.strftime("%-m/%-d/%Y") if os.name != "nt" else now.strftime("%m/%d/%Y")
        time_str = now.strftime("%I:%M:%S%p").lower().replace(" 0", " ")
        line = build_cap_line(self._header_parts, date_str, time_str, lux, spectral) + "\n"
        self._ensure_output_dir()
        with open(self._output_abs, "a", encoding="utf-8") as f:
            f.write(line)
        logger.debug("Jeti sim wrote row to %s lux=%.1f", self._output_abs, lux)

    def poll(self) -> Iterable[SensorReading]:
        """
        Emit one "measurement": write one .cap row to output_path and yield SensorReading(s).
        Advances through template rows; loops if configured.
        """
        if not self._template_rows:
            return
        lux, spectral = self._template_rows[self._row_index]
        ts = time.time()
        self._write_row(lux, spectral, ts)
        yield SensorReading(sensor_id=self._sensor_id, metric="lux", value=lux, ts=ts)

        self._row_index += 1
        if self._row_index >= len(self._template_rows):
            if self._loop:
                self._row_index = 0
            else:
                self._row_index = len(self._template_rows) - 1
