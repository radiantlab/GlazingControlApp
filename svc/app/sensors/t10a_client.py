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

# Fixed reply lengths from Konica Minolta T-10A communication spec.
_SHORT_REPLY_LEN = 14
_LONG_REPLY_LEN = 32


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
      - 9600 baud, 7 data bits, even parity, 1 stop bit (7E1).
      - ASCII framed commands with STX/ETX + BCC (BCC XORs body + ETX only).
      - Command '54' + param '1 ' -> PC mode (short 14-byte reply).
      - Command '10' + param '0200' -> measurement data output (32-byte reply).
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        heads: List[T10AHeadConfig],
        timeout_s: float = 1.0,
        protocol: dict | None = None,
        baudrate: int = 9600,
        open_delay_s: float = 0.2,
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
        # Konica Minolta spec: PC mode uses param "1 " (not "0000").
        self._pc_mode_params = str(protocol_cfg.get("pc_mode_params", "1 "))
        self._send_pc_mode = str(
            protocol_cfg.get("send_pc_mode", "true")
        ).lower() in {"1", "true", "yes", "on"}
        self._pc_mode_head_no = int(protocol_cfg.get("pc_mode_head_no", 0))
        self._short_reply_len = int(protocol_cfg.get("short_reply_len", _SHORT_REPLY_LEN))
        self._long_reply_len = int(protocol_cfg.get("long_reply_len", _LONG_REPLY_LEN))
        self._xonxoff = str(protocol_cfg.get("xonxoff", "true")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._inter_command_delay_s = float(protocol_cfg.get("inter_command_delay_s", 0.1))

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self._coerce_baudrate(protocol_cfg.get("baudrate"), baudrate),
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout_s,
            xonxoff=self._xonxoff,
        )
        logger.info(
            "T10AClient[%s] opened on %s (%s baud, 7E1, xonxoff=%s)",
            self.id,
            self.port,
            self.ser.baudrate,
            self._xonxoff,
        )

        if open_delay_s > 0:
            time.sleep(open_delay_s)

        # put meter into PC mode (command 54)
        if self._send_pc_mode:
            self._enter_pc_mode()

    # --- low-level helpers -------------------------------------------------

    @staticmethod
    def _compute_bcc(body_with_etx: bytes) -> bytes:
        """BCC = XOR of body characters + ETX (STX is excluded)."""
        bcc_val = 0
        for b in body_with_etx:
            bcc_val ^= b
        return f"{bcc_val:02X}".encode("ascii")

    @staticmethod
    def _coerce_baudrate(value, default: int = 9600) -> int:
        if value in (None, "") or str(value).strip().lower() == "auto":
            return int(default)
        return int(value)

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

        body_with_etx = body.encode("ascii") + b"\x03"
        bcc = self._compute_bcc(body_with_etx)
        return b"\x02" + body_with_etx + bcc + b"\r\n"

    @classmethod
    def _build_probe_frame(
        cls,
        *,
        head_no: int,
        cmd: str,
        params: str,
        protocol: dict | None = None,
    ) -> bytes:
        protocol_cfg = protocol or {}
        head_index_base = int(protocol_cfg.get("head_index_base", 0))
        body_template = str(protocol_cfg.get("body_template", "{head:02d}{cmd}{params}"))
        head_address = head_no + head_index_base
        body = body_template.format(
            head=head_address,
            head_no=head_no,
            cmd=cmd,
            params=params,
        )

        body_with_etx = body.encode("ascii") + b"\x03"
        bcc = cls._compute_bcc(body_with_etx)
        return b"\x02" + body_with_etx + bcc + b"\r\n"

    def _response_length_for(self, cmd: str) -> int:
        if cmd == self._measure_command:
            return self._long_reply_len
        return self._short_reply_len

    @staticmethod
    def _read_serial_reply(ser, expected_len: int) -> bytes:
        data = ser.read(expected_len)
        if len(data) < expected_len:
            # Fallback for adapters that chunk differently.
            extra = ser.read_until(expected=b"\r\n", size=max(expected_len, 64))
            if extra and not data.endswith(extra):
                data = (data + extra)[: max(expected_len, len(data + extra))]
        return data

    def _read_reply(self, cmd: str) -> str:
        """Read a fixed-length T-10A reply frame."""
        data = self._read_serial_reply(self.ser, self._response_length_for(cmd))
        return data.decode("ascii", errors="replace").strip()

    def _send_command(self, head_no: int, cmd: str, params: str = "") -> str:
        """Send a command and return the raw ASCII reply."""
        frame = self._build_frame(head_no, cmd, params=params)
        logger.debug("T10A[%s] TX %r", self.id, frame)
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        if self._inter_command_delay_s > 0:
            time.sleep(self._inter_command_delay_s)
        reply = self._read_reply(cmd)
        logger.debug("T10A[%s] RX %r", self.id, reply)
        return reply

    def _enter_pc_mode(self) -> None:
        """Send configured PC mode command once."""
        try:
            reply = self._send_command(
                head_no=self._pc_mode_head_no,
                cmd=self._pc_mode_command,
                params=self._pc_mode_params,
            )
            logger.info("T10A[%s] PC mode reply: %r", self.id, reply)
            if not reply:
                logger.warning(
                    "T10A[%s] empty PC mode reply on %s — check USB cable, "
                    "meter power, and that no other app holds the port",
                    self.id,
                    self.port,
                )
        except Exception as e:
            logger.error("T10A[%s] failed to enter PC mode: %s", self.id, e)

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

    @staticmethod
    def _parse_t10a_data_field(field: str) -> float | None:
        """
        Parse one 6-character Ev slot from a long measurement frame.

        Meters sometimes pad with spaces, e.g. '+ 2904' instead of '+02904'.
        """
        compact = field.replace(" ", "")
        if not compact or compact[0] not in "+-":
            return None
        if len(compact) == 5:
            # '+2904' -> '+02904' (insert mantissa leading zero)
            compact = compact[0] + "0" + compact[1:]
        if len(compact) != 6 or not compact[1:5].isdigit() or not compact[5].isdigit():
            return None
        sign = -1 if compact[0] == "-" else 1
        mant = int(compact[1:5])
        exp = int(compact[5]) - 4
        return float(sign * mant * (10**exp))

    @classmethod
    def _looks_like_t10a_reply(cls, raw: bytes, expected_cmd: str) -> bool:
        if not raw:
            return False
        text = raw.decode("ascii", errors="replace").strip()
        body = cls._strip_transport(text)
        if len(body) < 4:
            return False
        if body[:2].isdigit() and body[2:4] == expected_cmd:
            return True
        return body[:2].isdigit() and "ERR" in body.upper()

    @classmethod
    def probe_port(
        cls,
        *,
        port: str,
        timeout_s: float = 1.0,
        protocol: dict | None = None,
        baudrate: int = 9600,
        head_no: int = 0,
        open_delay_s: float = 0.1,
    ) -> bool:
        protocol_cfg = protocol or {}
        xonxoff = str(protocol_cfg.get("xonxoff", "true")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        inter_command_delay_s = float(protocol_cfg.get("inter_command_delay_s", 0.1))
        measure_command = str(protocol_cfg.get("measure_command", "10"))
        measure_params = str(protocol_cfg.get("measure_params", "0200"))
        pc_mode_command = str(protocol_cfg.get("pc_mode_command", "54"))
        pc_mode_params = str(protocol_cfg.get("pc_mode_params", "1 "))
        pc_mode_head_no = int(protocol_cfg.get("pc_mode_head_no", 0))
        short_reply_len = int(protocol_cfg.get("short_reply_len", _SHORT_REPLY_LEN))
        long_reply_len = int(protocol_cfg.get("long_reply_len", _LONG_REPLY_LEN))
        send_pc_mode = str(protocol_cfg.get("send_pc_mode", "true")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        commands: list[tuple[int, str, str, int]] = []
        if send_pc_mode:
            commands.append((pc_mode_head_no, pc_mode_command, pc_mode_params, short_reply_len))
        commands.append((head_no, measure_command, measure_params, long_reply_len))

        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=cls._coerce_baudrate(protocol_cfg.get("baudrate"), baudrate),
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout_s,
                xonxoff=xonxoff,
            )
            if open_delay_s > 0:
                time.sleep(open_delay_s)

            for probe_head_no, cmd, params, reply_len in commands:
                frame = cls._build_probe_frame(
                    head_no=probe_head_no,
                    cmd=cmd,
                    params=params,
                    protocol=protocol_cfg,
                )
                ser.reset_input_buffer()
                ser.write(frame)
                ser.flush()
                if inter_command_delay_s > 0:
                    time.sleep(inter_command_delay_s)
                raw = cls._read_serial_reply(ser, reply_len)
                if cls._looks_like_t10a_reply(raw, cmd):
                    return True
            return False
        except Exception as e:
            logger.debug("T10A probe failed on %s: %s", port, e)
            return False
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

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

            # T-10A long frame (no STX): head(2)+cmd(2)+status(4)+data1(6)+data2(6)+data3(6)
            for field in (body[8:14], body[14:20], body[20:26]):
                ev = self._parse_t10a_data_field(field)
                if ev is not None:
                    return ev

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
            logger.warning(
                "T10A[%s] parse error for %s: reply=%r err=%s",
                self.id,
                head_cfg.sensor_id,
                reply,
                e,
            )
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
                    logger.debug(
                        "T10A[%s] no lux parsed for head %s, reply=%r",
                        self.id,
                        head.head_no,
                        reply,
                    )
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
                logger.error("T10A[%s] poll failed for head %s: %s", self.id, head.head_no, e)

        return readings

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass
