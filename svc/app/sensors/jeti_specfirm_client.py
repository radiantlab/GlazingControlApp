from __future__ import annotations

import logging
import re
import time
from typing import Iterable

import serial

from .interface import SensorClient, SensorReading
from .spectral_metrics import compute_jeti_metrics

logger = logging.getLogger(__name__)

_FLOAT_RE = re.compile(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[Ee][+-]?\d+)?")


class JetiSpecfirmClient(SensorClient):
    """
    JETI spectraval/specbos polling via SPECFIRM SCPI-over-serial.

    Notes from SPECFIRM docs:
      - USB virtual COM, 8N1, no protocol
      - spectraval 1511 default baud: 921600
      - SCPI commands end with CR
      - ACK (0x06), BELL (0x07), NAK (0x15) control bytes may appear in responses
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        port: str,
        label: str,
        location: str | None = None,
        baudrate: int = 921600,
        timeout_s: float = 1.0,
        tint_ms: float = 100.0,
        avg_count: int = 1,
        wavelength_start_nm: int = 380,
        wavelength_end_nm: int = 780,
        wavelength_step_nm: int = 1,
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._label = label
        self._location = location
        self._tint_ms = float(tint_ms)
        self._avg_count = int(avg_count)
        self._w_start = int(wavelength_start_nm)
        self._w_end = int(wavelength_end_nm)
        self._w_step = int(wavelength_step_nm)
        self._expected_samples = (
            ((self._w_end - self._w_start) // self._w_step) + 1
            if self._w_step > 0 and self._w_end >= self._w_start
            else 0
        )
        self._configured = False

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout_s,
        )
        logger.info(
            "JetiSpecfirmClient[%s] opened %s (baud=%s, tint_ms=%s, avg=%s)",
            self.id,
            port,
            baudrate,
            self._tint_ms,
            self._avg_count,
        )

    def _read_until_idle(
        self,
        *,
        total_timeout_s: float = 4.0,
        idle_timeout_s: float = 0.10,
    ) -> bytes:
        deadline = time.monotonic() + total_timeout_s
        last_rx = time.monotonic()
        buf = bytearray()

        while time.monotonic() < deadline:
            chunk = self.ser.read(4096)
            if chunk:
                buf.extend(chunk)
                last_rx = time.monotonic()
                continue
            # no new bytes this read cycle
            if buf and (time.monotonic() - last_rx) >= idle_timeout_s:
                break
        return bytes(buf)

    def _send(self, command: str, *, timeout_s: float = 4.0) -> bytes:
        payload = command.encode("ascii") + b"\r"
        self.ser.reset_input_buffer()
        self.ser.write(payload)
        self.ser.flush()
        raw = self._read_until_idle(total_timeout_s=timeout_s)
        if b"\x15" in raw:
            logger.warning("JETI[%s] NAK for command %s", self.id, command)
        return raw

    def _extract_floats(self, raw: bytes) -> list[float]:
        # Remove common control bytes (ACK, BEL, NAK) before tokenizing.
        text = (
            raw.replace(b"\x06", b" ")
            .replace(b"\x07", b" ")
            .replace(b"\x15", b" ")
            .decode("latin-1", errors="ignore")
        )
        vals: list[float] = []
        for token in _FLOAT_RE.findall(text):
            try:
                vals.append(float(token))
            except ValueError:
                continue
        return vals

    def _configure_if_needed(self) -> None:
        if self._configured:
            return
        # Configure exported wavelength range and force ASCII spectrum output.
        self._send(
            f"*PARAmeter:WRANge {self._w_start} {self._w_end} {self._w_step}",
            timeout_s=1.5,
        )
        self._send("*PARAmeter:FORMat 2", timeout_s=1.5)
        self._configured = True

    def poll(self) -> Iterable[SensorReading]:
        try:
            self._configure_if_needed()
            # Take one reference measurement and output spectrum in ASCII format.
            # Command form from SPECFIRM docs:
            #   *MEASure:REFErence tint av format
            raw_spectrum = self._send(
                f"*MEASure:REFErence {self._tint_ms} {self._avg_count} 2",
                timeout_s=6.0,
            )
            spectral = self._extract_floats(raw_spectrum)
            if self._expected_samples > 0 and len(spectral) > (self._expected_samples + 10):
                # Keep the tail where spectrum values usually appear if extra tokens are present.
                spectral = spectral[-self._expected_samples :]
            elif self._expected_samples > 0 and len(spectral) >= self._expected_samples:
                spectral = spectral[: self._expected_samples]

            if len(spectral) < 10:
                logger.warning(
                    "JETI[%s] insufficient spectrum values (%d) in response",
                    self.id,
                    len(spectral),
                )
                return []

            # Photometric scalar for current measurement.
            raw_lux = self._send("*CALCulate:PHOTOmetric", timeout_s=2.0)
            lux = None
            for candidate in self._extract_floats(raw_lux):
                if candidate >= 0:
                    lux = candidate
                    break

            metrics = compute_jeti_metrics(lux=lux, spectral_values=spectral)
            ts = time.time()
            out: list[SensorReading] = []
            for metric, value in metrics.items():
                out.append(
                    SensorReading(
                        sensor_id=self._sensor_id,
                        metric=metric,
                        value=float(value),
                        ts=ts,
                    )
                )
            return out
        except Exception as e:
            logger.error("JETI[%s] serial poll failed: %s", self.id, e)
            return []

