from __future__ import annotations

import logging
import math
import struct
import time
from typing import Iterable

from pymodbus.client import ModbusTcpClient

from .interface import SensorClient, SensorReading

logger = logging.getLogger(__name__)


def _is_finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


class EkoCBoxModbusTcpClient(SensorClient):
    """
    EKO MS-90+ integration via C-BOX Ethernet Modbus TCP.

    The C-BOX owns the sensor-side wiring. The backend connects to the C-BOX
    over TCP and reads the same holding-register map used by the old decoder.
    """

    def __init__(
        self,
        *,
        device_id: str,
        sensor_id: str,
        host: str,
        port: int = 502,
        slave_address: int = 1,
        timeout_s: float = 3.0,
        label: str = "EKO MS-90+",
        location: str | None = None,
        float_byte_order: str = "ABCD",
    ) -> None:
        self.id = device_id
        self._sensor_id = sensor_id
        self._label = label
        self._location = location
        self._host = str(host).strip()
        self._port = int(port)
        self._slave = int(slave_address)
        self._timeout_s = float(timeout_s)
        self._float_byte_order = float_byte_order.upper()

        if not self._host:
            raise ValueError(f"EKO[{self.id}] missing Modbus TCP host/IP")
        if not (1 <= self._port <= 65535):
            raise ValueError(f"EKO[{self.id}] invalid Modbus TCP port: {self._port}")
        if not (1 <= self._slave <= 247):
            raise ValueError(f"EKO[{self.id}] invalid Modbus unit/slave address: {self._slave}")

        self._client = ModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=self._timeout_s,
        )
        try:
            connected = bool(self._client.connect())
        except Exception as e:
            logger.error(
                "EKO[%s] Modbus TCP connection failed to %s:%s: %s",
                self.id,
                self._host,
                self._port,
                e,
            )
            raise ConnectionError(
                f"EKO[{self.id}] Modbus TCP connection failed to {self._host}:{self._port}: {e}"
            ) from e

        if not connected:
            logger.error(
                "EKO[%s] Modbus TCP connection failed to %s:%s",
                self.id,
                self._host,
                self._port,
            )
            raise ConnectionError(
                f"EKO[{self.id}] Modbus TCP connection failed to {self._host}:{self._port}"
            )

        logger.info(
            "EkoCBoxModbusTcpClient[%s] connected to %s:%s (unit=%s)",
            self.id,
            self._host,
            self._port,
            self._slave,
        )

    def _read_holding_registers(self, start_addr: int, count: int) -> list[int]:
        if not (0 <= start_addr <= 0xFFFF):
            raise ValueError(f"start_addr out of range: {start_addr}")
        if not (1 <= count <= 125):
            raise ValueError(f"register count out of range: {count}")

        try:
            try:
                response = self._client.read_holding_registers(
                    address=start_addr,
                    count=count,
                    device_id=self._slave,
                )
            except TypeError:
                try:
                    response = self._client.read_holding_registers(
                        address=start_addr,
                        count=count,
                        slave=self._slave,
                    )
                except TypeError:
                    response = self._client.read_holding_registers(
                        start_addr,
                        count=count,
                        unit=self._slave,
                    )
        except Exception as e:
            raise ConnectionError(
                f"EKO[{self.id}] Modbus TCP read failed at {self._host}:{self._port} "
                f"start={start_addr} count={count}: {e}"
            ) from e

        if response is None:
            raise TimeoutError(
                f"EKO[{self.id}] Modbus TCP read returned no response at "
                f"{self._host}:{self._port} start={start_addr} count={count}"
            )

        is_error = getattr(response, "isError", None)
        if callable(is_error) and is_error():
            raise RuntimeError(
                f"EKO[{self.id}] Modbus TCP exception at {self._host}:{self._port} "
                f"start={start_addr} count={count}: {response}"
            )

        registers = getattr(response, "registers", None)
        if registers is None:
            raise ValueError(f"EKO[{self.id}] Modbus TCP response missing registers")
        if len(registers) != count:
            raise ValueError(
                f"EKO[{self.id}] Modbus TCP register count mismatch: "
                f"got={len(registers)} expected={count}"
            )
        return [int(r) & 0xFFFF for r in registers]

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
        # Addresses retained from the existing C-BOX register decoder:
        #   3  board temp x10 (word)
        #   4  GHI float
        #   6  DNI float
        #   10 NTC/sensor temp float
        #   12 DHI float
        #   14 timestamp uint32
        #   18 GPS sats word
        #   34 latitude float
        #   36 longitude float
        #   40 sun elevation float
        #   42 sun azimuth float
        try:
            base_block = self._read_holding_registers(start_addr=3, count=13)
            sats_block = self._read_holding_registers(start_addr=18, count=1)
            geo_block = self._read_holding_registers(start_addr=34, count=10)
        except Exception as e:
            logger.error("EKO[%s] Modbus TCP read failed: %s", self.id, e)
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

        try:
            metrics["board_temp_c"] = r(3) / 10.0

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
                value = f(addr)
                if _is_finite(value):
                    metrics[name] = value

            gps_ts = (r(14) << 16) | r(15)
            metrics["gps_timestamp_s"] = float(gps_ts)
            metrics["gps_satellites"] = float(r(18))
        except Exception as e:
            logger.error("EKO[%s] register decoding failed: %s", self.id, e)
            return []

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

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
