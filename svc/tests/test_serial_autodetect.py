from __future__ import annotations

from dataclasses import dataclass

from app.sensors import serial_autodetect


@dataclass
class FakePortInfo:
    device: str
    name: str = ""
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    location: str = ""
    vid: int | None = None
    pid: int | None = None


def test_find_serial_port_filters_match_hints_and_reserved_ports(monkeypatch) -> None:
    monkeypatch.setattr(
        serial_autodetect.list_ports,
        "comports",
        lambda: [
            FakePortInfo("COM10", description="Reserved T-10A", serial_number="T10A-01"),
            FakePortInfo(
                "COM3",
                description="USB Serial JETI",
                serial_number="JETI-ABC",
                vid=0x1234,
            ),
        ],
    )
    probed: list[str] = []

    port = serial_autodetect.find_serial_port(
        sensor_name="JETI",
        requested_port="auto",
        reserved_ports={"COM10"},
        match={"serial_number": "jeti-abc", "vid": "0x1234"},
        probe=lambda candidate_port: probed.append(candidate_port) or True,
    )

    assert port == "COM3"
    assert probed == ["COM3"]


def test_list_serial_port_candidates_uses_natural_com_order(monkeypatch) -> None:
    monkeypatch.setattr(
        serial_autodetect.list_ports,
        "comports",
        lambda: [
            FakePortInfo("COM10"),
            FakePortInfo("COM2"),
            FakePortInfo("COM1"),
        ],
    )

    candidates = serial_autodetect.list_serial_port_candidates()

    assert [candidate.device for candidate in candidates] == ["COM1", "COM2", "COM10"]
