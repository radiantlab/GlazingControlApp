from __future__ import annotations

from app.sensors.t10a_client import T10AClient, T10AHeadConfig


def _make_client_stub() -> T10AClient:
    # Build a lightweight instance without opening a serial port.
    c = T10AClient.__new__(T10AClient)
    c.id = "KMX"
    c._head_index_base = 0
    c._body_template = "{head:02d}{cmd}{params}"
    return c


def test_parse_measurement_reply_e_format() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "\x020010+0123E0\x03AA") == 123.0


def test_parse_measurement_reply_signed_exponent() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "\x020010+0123+1\x03AA") == 1230.0


def test_parse_measurement_reply_decimal_fallback() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "EV=67.9lx") == 67.9


def test_parse_measurement_reply_does_not_parse_header_integers() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "\x0200100200\x03AA") is None


def test_build_frame_contains_stx_etx_bcc() -> None:
    client = _make_client_stub()
    frame = client._build_frame(head_no=0, cmd="10", params="0200")
    assert frame.startswith(b"\x02")
    assert b"\x03" in frame
    assert frame.endswith(b"\r\n")
