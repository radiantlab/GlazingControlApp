# app/sensors/t10a_client.py
from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from typing import Iterable, List
import serial  # pip install pyserial

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


@dataclass
class T10AHeadConfig:
    head_no: int        # 0, 1, 2, 3 ...
    sensor_id: str      # "KM1-00", "KM1-01", etc.
    label: str          # for DB metadata
    location: str | None = None


class T10AClient(SensorClient):
    """
    Driver for a single Konica Minolta T-10A body with 1–4 sensor heads.
    One instance = one COM port = one meter (up to 4 heads daisy-chained).

    Based on T-10A Communication Specifications:
      - 9600 baud, 7 data bits, even parity, 1 stop bit.
      - ASCII framed commands with STX/ETX + BCC.
      - Command '54' → PC mode.
      - Command '10' → measurement data output (long frame).
    """

    def __init__(
        self,
        device_id: str,
        port: str,
        heads: List[T10AHeadConfig],
        timeout_s: float = 1.0,
    ) -> None:
        self.id = device_id      # e.g. "KM1"
        self.port = port
        self.heads = heads

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
        self._enter_pc_mode()

    # --- low-level helpers -------------------------------------------------

    def _build_frame(self, head_no: int, cmd: str) -> bytes:
        """
        Build a T-10A frame for given head + command.

        You MUST implement this exactly as in CS0103E:
          [STX] + body + [ETX] + BCC

        - body typically contains instrument address, receptor-head #, command code.
        - BCC is a 2-digit hex XOR checksum as specified in the doc.
        """
        # PSEUDO: you will fill this in exactly from the spec
        body = f"00{head_no:02d}{cmd}"  # Example only; check the doc!
        # compute BCC over STX+body+ETX (see spec for exact range)
        stx = "\x02"
        etx = "\x03"
        raw = (stx + body + etx).encode("ascii")

        bcc_val = 0
        for b in raw:
            bcc_val ^= b
        bcc = f"{bcc_val:02X}".encode("ascii")

        frame = raw + bcc + b"\r\n"
        return frame

    def _send_command(self, head_no: int, cmd: str) -> str:
        """Send a command and return the raw ASCII reply (without CRLF)."""
        frame = self._build_frame(head_no, cmd)
        self.ser.write(frame)
        self.ser.flush()
        line = self.ser.readline().decode("ascii", errors="replace").strip()
        return line

    def _enter_pc_mode(self) -> None:
        """Send command 54 once to enter PC mode."""
        try:
            # '54' is the PC mode command code in the spec.
            reply = self._send_command(head_no=0, cmd="54")
            logger.info(f"T10A[{self.id}] PC mode reply: {reply!r}")
        except Exception as e:
            logger.error(f"T10A[{self.id}] failed to enter PC mode: {e}")

    # --- parse replies -----------------------------------------------------

    def _parse_measurement_reply(self, head_cfg: T10AHeadConfig, reply: str) -> float | None:
        """
        Parse the long measurement frame for a given head, returning Ev [lux].

        The spec gives the exact field layout; roughly:
          STX + addr + head + '10' + status + sign + 4 digits + exponent + ... + ETX + BCC

        Here we assume we've already stripped STX/ETX/BCC and are looking at the body.
        You MUST adjust offsets based on the manual.
        """
        try:
            # Example based on typical format: sddddE±dd
            # You will replace this with proper slicing.
            # For illustration we search for the EV numeric substring:
            # find first '+' or '-' and take 6 chars, etc.
            idx = max(reply.find("+"), reply.find("-"))
            if idx == -1:
                return None
            numeric = reply[idx : idx + 7]  # e.g. "+0123E0"
            # crude parse: "+0123E0" -> 123 * 10**0
            sign = -1 if numeric[0] == "-" else 1
            mant = int(numeric[1:5])
            exponent = int(numeric[6:])
            value = sign * mant * (10 ** exponent)
            return float(value)
        except Exception as e:
            logger.warning(f"T10A[{self.id}] parse error for {head_cfg.sensor_id}: reply={reply!r} err={e}")
            return None

    # --- public API --------------------------------------------------------

    def poll(self) -> Iterable[SensorReading]:
        """
        Poll all configured heads once (command '10' = measurement output).
        Returns one SensorReading per head with metric 'lux'.
        """
        readings: list[SensorReading] = []
        now = time.time()

        for head in self.heads:
            try:
                reply = self._send_command(head.head_no, cmd="10")
                # strip STX/ETX/BCC here if your readline includes them
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
