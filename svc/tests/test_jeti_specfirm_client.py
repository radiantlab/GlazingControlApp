from __future__ import annotations

from app.sensors.jeti_specfirm_client import JetiSpecfirmClient


def test_extract_floats_strips_control_bytes() -> None:
    c = JetiSpecfirmClient.__new__(JetiSpecfirmClient)
    raw = b"\x06 1.0 2E+0 -3 \x07 \x15"
    vals = c._extract_floats(raw)
    assert vals == [1.0, 2.0, -3.0]
