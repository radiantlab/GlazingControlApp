from __future__ import annotations

from app.sensors.t10a_client import T10AClient, T10AHeadConfig


def _make_client_stub() -> T10AClient:
    # Build a lightweight instance without opening a serial port.
    c = T10AClient.__new__(T10AClient)
    c.id = "KMX"
    c._head_index_base = 0
    c._body_template = "{head:02d}{cmd}{params}"
    c._measure_command = "10"
    c._pc_mode_command = "54"
    return c


def test_compute_bcc_excludes_stx() -> None:
    # Reference frame body for PC mode on head 0: 00541<ETX>
    body_with_etx = b"00541 \x03"
    assert T10AClient._compute_bcc(body_with_etx) == b"13"


def test_build_pc_mode_frame_matches_spec() -> None:
    client = _make_client_stub()
    frame = client._build_frame(head_no=0, cmd="54", params="1 ")
    assert frame == b"\x0200541 \x0313\r\n"


def test_build_measure_frame_head_zero() -> None:
    client = _make_client_stub()
    frame = client._build_frame(head_no=0, cmd="10", params="0200")
    assert frame.startswith(b"\x0200100200\x03")
    assert frame.endswith(b"\r\n")


def test_parse_measurement_reply_e_format() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "\x020010+0123E0\x03AA") == 123.0


def test_parse_measurement_reply_signed_exponent() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "\x020010+0123+1\x03AA") == 1230.0


def test_parse_measurement_reply_t10a_fixed_field() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    # Long frame: head(2)+cmd(2)+status(4)+data1(6); exp digit 4 => 10^(4-4)
    reply = "\x02" + "00" + "10" + "0000" + "+01234" + "      " + "      " + "\x03AA"
    assert client._parse_measurement_reply(head, reply) == 123.0


def test_parse_measurement_reply_t10a_unsigned_zero_field() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    reply = "\x02" + "00" + "10" + "0000" + "000004" + "      " + "      " + "\x03AA"
    assert client._parse_measurement_reply(head, reply) == 0.0


def test_parse_measurement_reply_decimal_fallback() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "EV=67.9lx") == 67.9


def test_parse_measurement_reply_plain_zero_with_unit() -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    assert client._parse_measurement_reply(head, "EV=0 lx") == 0.0


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


def test_poll_emits_zero_lux_reading(monkeypatch) -> None:
    client = _make_client_stub()
    head = T10AHeadConfig(head_no=0, sensor_id="KMX-00", label="x")
    client.heads = [head]
    client._measure_params = "0200"

    reply = "\x02" + "00" + "10" + "0000" + "000004" + "      " + "      " + "\x03AA"
    monkeypatch.setattr(client, "_send_command", lambda head_no, cmd, params: reply)

    readings = list(client.poll())

    assert len(readings) == 1
    assert readings[0].sensor_id == "KMX-00"
    assert readings[0].metric == "lux"
    assert readings[0].value == 0.0
