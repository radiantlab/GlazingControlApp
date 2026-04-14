from __future__ import annotations

from app.sensors.jeti_specfirm_client import JetiSpecfirmClient


def test_extract_floats_strips_control_bytes() -> None:
    c = JetiSpecfirmClient.__new__(JetiSpecfirmClient)
    raw = b"\x06 1.0 2E+0 -3 \x07 \x15"
    vals = c._extract_floats(raw)
    assert vals == [1.0, 2.0, -3.0]


def test_extract_spectrum_values_reads_ascii_wavelength_value_pairs() -> None:
    c = JetiSpecfirmClient.__new__(JetiSpecfirmClient)
    c._w_start = 380
    c._w_end = 382
    c._w_step = 1
    c._expected_samples = 3

    raw = (
        b"\x06"
        b"380\t1.25\r"
        b"381\t2.50\r"
        b"382\t3.75\r"
        b"\x03\r\r"
    )

    vals = c._extract_spectrum_values(raw)
    assert vals == [1.25, 2.5, 3.75]


def test_extract_spectrum_values_falls_back_to_flat_float_stream() -> None:
    c = JetiSpecfirmClient.__new__(JetiSpecfirmClient)
    c._w_start = 380
    c._w_end = 382
    c._w_step = 1
    c._expected_samples = 3

    raw = b"\x06 10 20 30 \x07"

    vals = c._extract_spectrum_values(raw)
    assert vals == [10.0, 20.0, 30.0]
