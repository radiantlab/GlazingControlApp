from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.sensors.serial_discovery import (
    InvalidSerialPortSelector,
    SerialDiscoveryError,
    SerialPortAmbiguousError,
    SerialPortInfo,
    SerialPortNotFoundError,
    SerialPortSelector,
    enumerate_serial_ports,
    format_serial_port_inventory,
    resolve_serial_port,
)


def _raw_port(device: str, **overrides):
    values = {
        "device": device,
        "name": device,
        "description": None,
        "hwid": None,
        "vid": None,
        "pid": None,
        "serial_number": None,
        "manufacturer": None,
        "product": None,
        "location": None,
        "interface": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _port(device: str, **overrides) -> SerialPortInfo:
    return SerialPortInfo.from_pyserial(_raw_port(device, **overrides))


def test_enumeration_captures_usb_identity_and_sorts_com_ports_naturally() -> None:
    raw_ports = [
        _raw_port("COM10", description="JETI"),
        _raw_port(
            "COM2",
            description="T-10A meter",
            hwid="USB VID:PID=0403:6001 SER=A100",
            vid=0x0403,
            pid=0x6001,
            serial_number="A100",
            manufacturer="FTDI",
            product="USB Serial Port",
            location="1-3.2",
            interface="MI_00",
        ),
    ]

    result = enumerate_serial_ports(port_provider=lambda: raw_ports)

    assert [item.device for item in result] == ["COM2", "COM10"]
    assert result[0].as_dict() == {
        "device": "COM2",
        "name": "COM2",
        "description": "T-10A meter",
        "hwid": "USB VID:PID=0403:6001 SER=A100",
        "vid": 0x0403,
        "pid": 0x6001,
        "serial_number": "A100",
        "manufacturer": "FTDI",
        "product": "USB Serial Port",
        "location": "1-3.2",
        "interface": "MI_00",
    }


def test_explicit_windows_port_matching_is_case_insensitive_and_accepts_prefix() -> None:
    ports = [_port("COM11"), _port("COM12")]

    selected = resolve_serial_port(
        SerialPortSelector(port=r"\\.\com12"),
        ports=ports,
        platform_name="win32",
    )

    assert selected.device == "COM12"


def test_identity_config_resolves_port_after_com_number_changes() -> None:
    ports = [
        _port(
            "COM4",
            vid=0x0403,
            pid=0x6001,
            serial_number="T10-A-001",
            manufacturer="FTDI",
            product="USB Serial Port",
            location="Port_#0001.Hub_#0002",
            hwid="USB VID:PID=0403:6001 SER=T10-A-001",
        ),
        _port(
            "COM8",
            vid=0x0403,
            pid=0x6001,
            serial_number="T10-A-002",
            manufacturer="FTDI",
            product="USB Serial Port",
            location="Port_#0002.Hub_#0002",
            hwid="USB VID:PID=0403:6001 SER=T10-A-002",
        ),
    ]
    config = {
        "port": "auto",
        "port_identity": {
            "vid": "0403",
            "pid": "0x6001",
            "serial_number": "t10-a-002",
            "manufacturer": "ftdi",
            "product": "usb serial port",
            "location": "port_#0002.hub_#0002",
            "hwid": "usb vid:pid=0403:6001 ser=t10-a-002",
        },
    }

    selected = resolve_serial_port(config, ports=ports, platform_name="win32")

    assert selected.device == "COM8"


def test_explicit_port_plus_identity_guards_against_replaced_device() -> None:
    selector = SerialPortSelector(
        port="COM4",
        serial_number="EXPECTED",
    )
    ports = [_port("COM4", serial_number="REPLACEMENT")]

    with pytest.raises(SerialPortNotFoundError) as exc_info:
        resolve_serial_port(selector, ports=ports, platform_name="win32")

    message = str(exc_info.value)
    assert "COM4" in message
    assert "serial_number is 'REPLACEMENT', expected 'EXPECTED'" in message


def test_ambiguous_identity_fails_instead_of_selecting_first_port() -> None:
    selector = SerialPortSelector(vid=0x0403, pid=0x6001)
    ports = [
        _port("COM8", vid=0x0403, pid=0x6001),
        _port("COM3", vid=0x0403, pid=0x6001),
    ]

    with pytest.raises(SerialPortAmbiguousError) as exc_info:
        resolve_serial_port(selector, ports=ports, platform_name="win32")

    message = str(exc_info.value)
    assert "matched 2 ports" in message
    assert message.index("COM3") < message.index("COM8")
    assert "serial_number, location, or an explicit port" in message


def test_not_found_diagnostics_include_inventory_and_each_mismatch() -> None:
    selector = SerialPortSelector(vid=0x1234, product="Expected")
    ports = [
        _port("COM5", vid=0x9999, product="Other", hwid="USB OTHER"),
    ]

    with pytest.raises(SerialPortNotFoundError) as exc_info:
        resolve_serial_port(selector, ports=ports, platform_name="win32")

    message = str(exc_info.value)
    assert "Detected serial ports on win32" in message
    assert "vid:pid=0x9999:<unknown>" in message
    assert "vid is 0x9999, expected 0x1234" in message
    assert "product is 'Other', expected 'Expected'" in message


def test_empty_non_windows_inventory_is_reported_without_platform_failure() -> None:
    assert (
        format_serial_port_inventory([], platform_name="linux")
        == "Detected serial ports on linux: <none>. Discovery is metadata-only "
        "and does not open devices."
    )

    with pytest.raises(SerialPortNotFoundError, match="on linux: <none>"):
        resolve_serial_port(
            SerialPortSelector(port="/dev/ttyUSB0"),
            ports=[],
            platform_name="linux",
        )


def test_non_windows_device_paths_remain_case_sensitive() -> None:
    ports = [_port("/dev/ttyUSB0")]

    assert (
        resolve_serial_port(
            SerialPortSelector(port="/dev/ttyUSB0"),
            ports=ports,
            platform_name="linux",
        ).device
        == "/dev/ttyUSB0"
    )
    with pytest.raises(SerialPortNotFoundError):
        resolve_serial_port(
            SerialPortSelector(port="/dev/ttyusb0"),
            ports=ports,
            platform_name="linux",
        )


def test_discovery_only_reads_metadata_and_never_probes_port() -> None:
    class MetadataOnlyPort:
        device = "COM9"
        name = "COM9"
        description = "Safe metadata"
        hwid = None
        vid = 0x1234
        pid = 0x5678
        serial_number = "SAFE"
        manufacturer = None
        product = None
        location = None
        interface = None

        def open(self):
            raise AssertionError("discovery must not open a port")

        def write(self, _payload):
            raise AssertionError("discovery must not write to a port")

    result = enumerate_serial_ports(port_provider=lambda: [MetadataOnlyPort()])

    assert result[0].serial_number == "SAFE"


def test_invalid_config_selector_reports_actionable_errors() -> None:
    with pytest.raises(InvalidSerialPortSelector, match="requires an explicit port"):
        SerialPortSelector.from_config({"port": "auto"})

    with pytest.raises(InvalidSerialPortSelector, match="Unsupported"):
        SerialPortSelector.from_config(
            {"port_identity": {"serial": "use-serial_number"}}
        )

    with pytest.raises(InvalidSerialPortSelector, match="must be an object"):
        SerialPortSelector.from_config({"port_identity": "not-an-object"})

    with pytest.raises(InvalidSerialPortSelector, match="hexadecimal USB ID"):
        SerialPortSelector(vid="not-hex")  # type: ignore[arg-type]


def test_provider_failure_is_wrapped_with_platform_context() -> None:
    def fail():
        raise OSError("registry unavailable")

    with pytest.raises(SerialDiscoveryError, match="Unable to enumerate serial ports"):
        enumerate_serial_ports(port_provider=fail)
