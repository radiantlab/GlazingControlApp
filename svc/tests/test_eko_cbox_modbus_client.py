from __future__ import annotations

import pytest

from app.sensors.eko_cbox_modbus_client import EkoCBoxModbusClient, _crc16_modbus


def test_crc16_modbus_known_vector() -> None:
    # Standard Modbus frame body: 01 03 00 00 00 0A -> CRC 0xCDC5 (C5 CD on wire)
    payload = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
    assert _crc16_modbus(payload) == 0xCDC5


def test_decode_float32_abcd() -> None:
    c = EkoCBoxModbusClient.__new__(EkoCBoxModbusClient)
    c.id = "EKO"
    c._float_byte_order = "ABCD"
    # 1.0f = 0x3F800000
    assert c._decode_float32(0x3F80, 0x0000) == pytest.approx(1.0)


def test_decode_float32_cdab() -> None:
    c = EkoCBoxModbusClient.__new__(EkoCBoxModbusClient)
    c.id = "EKO"
    c._float_byte_order = "CDAB"
    # For CDAB order, provide regs so bytes become 3F 80 00 00.
    assert c._decode_float32(0x0000, 0x3F80) == pytest.approx(1.0)


def test_decode_float32_invalid_order_raises() -> None:
    c = EkoCBoxModbusClient.__new__(EkoCBoxModbusClient)
    c.id = "EKO"
    c._float_byte_order = "ZZZZ"
    with pytest.raises(ValueError):
        c._decode_float32(0x0000, 0x0000)
