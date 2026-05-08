from __future__ import annotations

import struct

import pytest

import app.sensors.eko_cbox_modbus_tcp_client as eko_tcp
from app.sensors.eko_cbox_modbus_tcp_client import EkoCBoxModbusTcpClient


class FakeReadResponse:
    def __init__(self, registers: list[int], error: bool = False) -> None:
        self.registers = registers
        self._error = error

    def isError(self) -> bool:
        return self._error


class FakeModbusTcpClient:
    instances: list["FakeModbusTcpClient"] = []

    def __init__(self, *, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list[tuple[int, int, int]] = []
        FakeModbusTcpClient.instances.append(self)

    def connect(self) -> bool:
        return True

    def read_holding_registers(self, *, address: int, count: int, slave: int):
        self.calls.append((address, count, slave))
        return FakeReadResponse([0] * count)

    def close(self) -> None:
        pass


def _client_without_socket() -> EkoCBoxModbusTcpClient:
    c = EkoCBoxModbusTcpClient.__new__(EkoCBoxModbusTcpClient)
    c.id = "EKO"
    c._sensor_id = "EKO-00"
    c._float_byte_order = "ABCD"
    return c


def _float_regs(value: float) -> tuple[int, int]:
    raw = struct.pack(">f", value)
    return ((raw[0] << 8) | raw[1], (raw[2] << 8) | raw[3])


def test_tcp_client_uses_host_port_timeout_and_unit(monkeypatch) -> None:
    FakeModbusTcpClient.instances.clear()
    monkeypatch.setattr(eko_tcp, "ModbusTcpClient", FakeModbusTcpClient)

    client = EkoCBoxModbusTcpClient(
        device_id="EKO-CBOX-01",
        sensor_id="EKO-00",
        host="192.168.2.20",
        port=502,
        slave_address=1,
        timeout_s=3.0,
    )

    assert client._read_holding_registers(3, 2) == [0, 0]
    fake = FakeModbusTcpClient.instances[0]
    assert (fake.host, fake.port, fake.timeout) == ("192.168.2.20", 502, 3.0)
    assert fake.calls == [(3, 2, 1)]


def test_missing_host_raises_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(eko_tcp, "ModbusTcpClient", FakeModbusTcpClient)

    with pytest.raises(ValueError, match="missing Modbus TCP host"):
        EkoCBoxModbusTcpClient(
            device_id="EKO-CBOX-01",
            sensor_id="EKO-00",
            host="",
        )


def test_decode_float32_abcd() -> None:
    c = _client_without_socket()
    assert c._decode_float32(0x3F80, 0x0000) == pytest.approx(1.0)


def test_decode_float32_cdab() -> None:
    c = _client_without_socket()
    c._float_byte_order = "CDAB"
    assert c._decode_float32(0x0000, 0x3F80) == pytest.approx(1.0)


def test_decode_float32_invalid_order_raises() -> None:
    c = _client_without_socket()
    c._float_byte_order = "ZZZZ"
    with pytest.raises(ValueError):
        c._decode_float32(0x0000, 0x0000)


def test_register_decoding_emits_expected_metric_names(monkeypatch) -> None:
    c = _client_without_socket()
    values = {
        "ghi_w_m2": _float_regs(904.755),
        "dni_w_m2": _float_regs(855.298),
        "sensor_temp_c": _float_regs(24.838),
        "dhi_w_m2": _float_regs(148.506),
        "latitude_deg": _float_regs(44.563),
        "longitude_deg": _float_regs(-123.288),
        "sun_elevation_deg": _float_regs(61.885),
        "sun_azimuth_deg": _float_regs(189.573),
    }

    reg_map = {
        3: 235,
        4: values["ghi_w_m2"][0],
        5: values["ghi_w_m2"][1],
        6: values["dni_w_m2"][0],
        7: values["dni_w_m2"][1],
        10: values["sensor_temp_c"][0],
        11: values["sensor_temp_c"][1],
        12: values["dhi_w_m2"][0],
        13: values["dhi_w_m2"][1],
        14: 0x0001,
        15: 0x0002,
        18: 11,
        34: values["latitude_deg"][0],
        35: values["latitude_deg"][1],
        36: values["longitude_deg"][0],
        37: values["longitude_deg"][1],
        40: values["sun_elevation_deg"][0],
        41: values["sun_elevation_deg"][1],
        42: values["sun_azimuth_deg"][0],
        43: values["sun_azimuth_deg"][1],
    }

    def fake_read(start_addr: int, count: int) -> list[int]:
        return [reg_map.get(addr, 0) for addr in range(start_addr, start_addr + count)]

    monkeypatch.setattr(c, "_read_holding_registers", fake_read)

    readings = list(c.poll())
    metrics = {r.metric: r.value for r in readings}

    assert set(metrics) == {
        "ghi_w_m2",
        "dni_w_m2",
        "dhi_w_m2",
        "board_temp_c",
        "sensor_temp_c",
        "gps_timestamp_s",
        "gps_satellites",
        "latitude_deg",
        "longitude_deg",
        "sun_elevation_deg",
        "sun_azimuth_deg",
    }
    assert metrics["board_temp_c"] == pytest.approx(23.5)
    assert metrics["ghi_w_m2"] == pytest.approx(904.755, rel=1e-6)
    assert metrics["gps_timestamp_s"] == pytest.approx(65538.0)
    assert metrics["gps_satellites"] == pytest.approx(11.0)


def test_poll_logs_modbus_read_failure(monkeypatch, caplog) -> None:
    c = _client_without_socket()

    def fake_read(start_addr: int, count: int) -> list[int]:
        raise TimeoutError("no response")

    monkeypatch.setattr(c, "_read_holding_registers", fake_read)

    with caplog.at_level("ERROR"):
        assert list(c.poll()) == []

    assert "Modbus TCP read failed" in caplog.text
    assert "no response" in caplog.text


def test_poll_logs_register_decoding_failure(monkeypatch, caplog) -> None:
    c = _client_without_socket()
    c._float_byte_order = "ZZZZ"
    monkeypatch.setattr(c, "_read_holding_registers", lambda start_addr, count: [0] * count)

    with caplog.at_level("ERROR"):
        assert list(c.poll()) == []

    assert "register decoding failed" in caplog.text
