# app/sensors/t10a_client.py
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable, List

import serial  # pip install pyserial

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


@dataclass
class T10AHeadConfig:
    head_no: int        # 0, 1, 2, 3 ...
    sensor_id: str      # "T10A1-H1", "T10A1-H2", etc.
    label: str          # for DB metadata
    location: str | None = None


class T10AClient(SensorClient):
    """
    Driver for a single Konica Minolta T-10A body with one or more sensor heads.
    One instance = one COM port = one meter.

    Based on T-10A Communication Specifications:
      - 9600 baud, 7 data bits, even parity, 1 stop bit.
      - ASCII framed commands with STX/ETX + BCC.
      - Command '54' -> PC mode.
      - Command '10' -> measurement data output (long frame).
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        heads: List[T10AHeadConfig],
        timeout_s: float = 1.0,
        protocol: dict | None = None,
    ) -> None:
        self.id = device_id      # e.g. "KM1"
        self.port = port
        self.heads = heads

        protocol_cfg = protocol or {}
        self._head_index_base = int(protocol_cfg.get("head_index_base", 0))
        self._body_template = str(
            protocol_cfg.get("body_template", "{head:02d}{cmd}{params}")
        )
        self._measure_command = str(protocol_cfg.get("measure_command", "10"))
        self._measure_params = str(protocol_cfg.get("measure_params", "0200"))
        self._pc_mode_command = str(protocol_cfg.get("pc_mode_command", "54"))
        self._pc_mode_params = str(protocol_cfg.get("pc_mode_params", "0000"))
        self._send_pc_mode = str(
            protocol_cfg.get("send_pc_mode", "true")
        ).lower() in {"1", "true", "yes", "on"}
        self._pc_mode_head_no = int(protocol_cfg.get("pc_mode_head_no", 0))

        self.ser = serial.Serial(
            port=self.port,
            baudrate=9600,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout_s,
        )
        logger.info(f"T10AClient[{self.id}] opened on {self.port}")

        # put meter into PC mode (command 54)
        if self._send_pc_mode:
            self._enter_pc_mode()

    # --- low-level helpers -------------------------------------------------

    def _build_frame(self, head_no: int, cmd: str, params: str = "") -> bytes:
        """
        Build a T-10A frame for given head + command.

        Frame format:
          [STX] + body + [ETX] + BCC + CRLF

        Body layout is configurable through `body_template`:
          default: "{head:02d}{cmd}{params}"
        where `head` is `head_no + head_index_base`.
        """
        head_address = head_no + self._head_index_base
        body = self._body_template.format(
            head=head_address,
            head_no=head_no,
            cmd=cmd,
            params=params,
        )

        stx = "\x02"
        etx = "\x03"
        raw = (stx + body + etx).encode("ascii")

        bcc_val = 0
        for b in raw:
            bcc_val ^= b
        bcc = f"{bcc_val:02X}".encode("ascii")

        frame = raw + bcc + b"\r\n"
        return frame

    def _send_command(self, head_no: int, cmd: str, params: str = "") -> str:
        """Send a command and return the raw ASCII reply (without CRLF)."""
        frame = self._build_frame(head_no, cmd, params=params)
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        line = self.ser.read_until(expected=b"\r\n").decode("ascii", errors="replace").strip()
        return line

    def _enter_pc_mode(self) -> None:
        """Send configured PC mode command once."""
        try:
            reply = self._send_command(
                head_no=self._pc_mode_head_no,
                cmd=self._pc_mode_command,
                params=self._pc_mode_params,
            )
            logger.info(f"T10A[{self.id}] PC mode reply: {reply!r}")
        except Exception as e:
            logger.error(f"T10A[{self.id}] failed to enter PC mode: {e}")

    # --- parse replies -----------------------------------------------------

    @staticmethod
    def _strip_transport(reply: str) -> str:
        s = reply.strip()
        if s.startswith("\x02"):
            s = s[1:]
        etx_idx = s.find("\x03")
        if etx_idx >= 0:
            s = s[:etx_idx]
        return s

    def _parse_measurement_reply(self, head_cfg: T10AHeadConfig, reply: str) -> float | None:
        """
        Parse a long measurement frame for a head and return Ev [lux].

        Handles common reply token shapes such as:
          +0123E0, +0123+0, scientific notation, or plain decimal.
        """
        try:
            body = self._strip_transport(reply)
            if not body:
                return None

            if "ERR" in body.upper():
                return None

            # Pattern 1: +0123E0 or -0123E+1
            m = re.search(r"([+-])(\d{4})(?:E)([+-]?\d{1,2})", body)
            if m:
                sign = -1 if m.group(1) == "-" else 1
                mant = int(m.group(2))
                exp = int(m.group(3))
                return float(sign * mant * (10 ** exp))

            # Pattern 2: +0123+0 / -0123-1
            m = re.search(r"([+-])(\d{4})([+-]\d{1,2})", body)
            if m:
                sign = -1 if m.group(1) == "-" else 1
                mant = int(m.group(2))
                exp = int(m.group(3))
                return float(sign * mant * (10 ** exp))

            # Pattern 3: standard scientific float token.
            m = re.search(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)[Ee][+-]?\d+", body)
            if m:
                return float(m.group(0))

            # Pattern 4: plain decimal token only (avoid accidental parsing of header integers).
            m = re.search(r"[+-]?(?:\d+\.\d*|\d*\.\d+)", body)
            if m:
                return float(m.group(0))

            return None
        except Exception as e:
            logger.warning(f"T10A[{self.id}] parse error for {head_cfg.sensor_id}: reply={reply!r} err={e}")
            return None

    # --- public API --------------------------------------------------------

    def poll(self) -> Iterable[SensorReading]:
        """
        Poll all configured heads once.

        Returns one SensorReading per head with metric 'lux'.
        """
        readings: list[SensorReading] = []
        now = time.time()

        for head in self.heads:
            try:
                reply = self._send_command(
                    head.head_no,
                    cmd=self._measure_command,
                    params=self._measure_params,
                )
                ev = self._parse_measurement_reply(head, reply)
                if ev is None:
                    continue
                readings.append(
                    SensorReading(
                        sensor_id=head.sensor_id,
                        metric="lux",
                        value=ev,
                        ts=now,
                    )
                )
            except Exception as e:
                logger.error(f"T10A[{self.id}] poll failed for head {head.head_no}: {e}")

        return readings

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass
