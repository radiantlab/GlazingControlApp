from __future__ import annotations

import logging
import math
import struct
import time
from typing import Iterable

import serial

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


def _crc16_modbus(payload: bytes) -> int:
    """
    Compute MODBUS RTU CRC16 (poly 0xA001, init 0xFFFF).

    Returned integer is little-endian when serialized in frame:
      low byte first, then high byte.
    """
    crc = 0xFFFF
    for b in payload:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _is_finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


class EkoCBoxModbusClient(SensorClient):
    """
    EKO MS-90+ integration via C-BOX Modbus RTU over RS-485.

    Based on local manual notes:
      - RS-485 Modbus RTU
      - Default: 9600, 8N1, parity none, slave/node 1
      - Register map includes GHI, DNI, DHI and metadata
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        port: str,
        slave_address: int = 1,
        baudrate: int = 9600,
        timeout_s: float = 1.0,
        label: str = "EKO MS-90+",
        location: str | None = None,
        float_byte_order: str = "ABCD",
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._label = label
        self._location = location
        self._port = port
        self._slave = int(slave_address)
        self._float_byte_order = float_byte_order.upper()

        if not (1 <= self._slave <= 247):
            raise ValueError(f"Invalid MODBUS slave address: {self._slave}")

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout_s,
        )
        logger.info(
            "EkoCBoxModbusClient[%s] opened %s (slave=%s, baud=%s)",
            self.id,
            self._port,
            self._slave,
            baudrate,
        )

    def _build_read_holding_frame(self, start_addr: int, count: int) -> bytes:
        if not (0 <= start_addr <= 0xFFFF):
            raise ValueError(f"start_addr out of range: {start_addr}")
        if not (1 <= count <= 125):
            raise ValueError(f"register count out of range: {count}")
        pdu = bytes(
            [
                self._slave,
                0x03,  # read holding registers
                (start_addr >> 8) & 0xFF,
                start_addr & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
            ]
        )
        crc = _crc16_modbus(pdu)
        return pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _read_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def _read_holding_registers(self, start_addr: int, count: int) -> list[int]:
        frame = self._build_read_holding_frame(start_addr=start_addr, count=count)
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()

        expected_len = 5 + (2 * count)
        response = self._read_exact(expected_len)
        if len(response) != expected_len:
            raise TimeoutError(
                f"EKO[{self.id}] short MODBUS response: got={len(response)} expected={expected_len}"
            )

        body = response[:-2]
        recv_crc_lo = response[-2]
        recv_crc_hi = response[-1]
        recv_crc = recv_crc_lo | (recv_crc_hi << 8)
        calc_crc = _crc16_modbus(body)
        if recv_crc != calc_crc:
            raise ValueError(
                f"EKO[{self.id}] bad CRC: recv=0x{recv_crc:04X} calc=0x{calc_crc:04X}"
            )

        slave = response[0]
        func = response[1]
        if slave != self._slave:
            raise ValueError(f"EKO[{self.id}] wrong slave in response: {slave}")

        # Modbus exception response.
        if func & 0x80:
            exc_code = response[2]
            raise ValueError(f"EKO[{self.id}] Modbus exception code={exc_code}")

        if func != 0x03:
            raise ValueError(f"EKO[{self.id}] wrong function code: {func}")

        byte_count = response[2]
        if byte_count != 2 * count:
            raise ValueError(
                f"EKO[{self.id}] byte count mismatch: {byte_count} vs {2 * count}"
            )

        data = response[3 : 3 + byte_count]
        regs: list[int] = []
        for i in range(0, len(data), 2):
            regs.append((data[i] << 8) | data[i + 1])
        return regs

    def _decode_float32(self, reg_hi: int, reg_lo: int) -> float:
        a = (reg_hi >> 8) & 0xFF
        b = reg_hi & 0xFF
        c = (reg_lo >> 8) & 0xFF
        d = reg_lo & 0xFF

        order = self._float_byte_order
        if order == "ABCD":
            raw = bytes([a, b, c, d])
        elif order == "CDAB":
            raw = bytes([c, d, a, b])
        elif order == "BADC":
            raw = bytes([b, a, d, c])
        elif order == "DCBA":
            raw = bytes([d, c, b, a])
        else:
            raise ValueError(
                f"EKO[{self.id}] unsupported float byte order '{self._float_byte_order}'"
            )

        return struct.unpack(">f", raw)[0]

    def poll(self) -> Iterable[SensorReading]:
        now = time.time()
        # Read key C-BOX map entries in small blocks for better compatibility with
        # devices that reject large/unused register spans.
        # Addresses (manual):
        #   3  board temp x10 (word)
        #   4  GHI float
        #   6  DNI float
        #   10 NTC float
        #   12 DHI float
        #   14 timestamp uint32
        #   18 GPS sats word
        #   34 lat float
        #   36 lon float
        #   40 elevation float
        #   42 azimuth float
        try:
            base_block = self._read_holding_registers(start_addr=3, count=13)   # 3..15
            sats_block = self._read_holding_registers(start_addr=18, count=1)   # 18
            geo_block = self._read_holding_registers(start_addr=34, count=10)   # 34..43
        except Exception as e:
            logger.error("EKO[%s] poll failed: %s", self.id, e)
            return []

        reg_map: dict[int, int] = {}
        for i, value in enumerate(base_block):
            reg_map[3 + i] = value
        reg_map[18] = sats_block[0]
        for i, value in enumerate(geo_block):
            reg_map[34 + i] = value

        def r(addr: int) -> int:
            if addr not in reg_map:
                raise KeyError(f"register {addr} missing in response")
            return reg_map[addr]

        def f(addr: int) -> float:
            return self._decode_float32(r(addr), r(addr + 1))

        metrics: dict[str, float] = {}

        board_temp_c = r(3) / 10.0
        metrics["board_temp_c"] = board_temp_c

        for name, addr in (
            ("ghi_w_m2", 4),
            ("dni_w_m2", 6),
            ("sensor_temp_c", 10),
            ("dhi_w_m2", 12),
            ("latitude_deg", 34),
            ("longitude_deg", 36),
            ("sun_elevation_deg", 40),
            ("sun_azimuth_deg", 42),
        ):
            try:
                value = f(addr)
                if _is_finite(value):
                    metrics[name] = value
            except Exception as e:
                logger.debug("EKO[%s] failed to decode %s: %s", self.id, name, e)

        gps_ts = (r(14) << 16) | r(15)
        gps_sats = float(r(18))
        metrics["gps_timestamp_s"] = float(gps_ts)
        metrics["gps_satellites"] = gps_sats

        out: list[SensorReading] = []
        for metric, value in metrics.items():
            out.append(
                SensorReading(
                    sensor_id=self._sensor_id,
                    metric=metric,
                    value=float(value),
                    ts=now,
                )
            )
        return out

