"""Safe serial-port discovery and deterministic configuration matching.

Discovery in this module is metadata-only.  It asks pyserial for the operating
system's port inventory but never opens a port, changes line settings, or sends
bytes to a device.  Protocol-specific probing belongs in the sensor drivers and
must be an explicit operator action.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from serial.tools import list_ports


_COM_PORT_RE = re.compile(r"^(?:\\\\\.\\)?COM(\d+)$", re.IGNORECASE)
_IDENTITY_FIELDS = (
    "vid",
    "pid",
    "serial_number",
    "manufacturer",
    "product",
    "location",
    "hwid",
)
_TEXT_IDENTITY_FIELDS = _IDENTITY_FIELDS[2:]


class SerialDiscoveryError(RuntimeError):
    """Base class for serial discovery failures."""


class InvalidSerialPortSelector(ValueError):
    """Raised when a serial-port selector is empty or malformed."""


class SerialPortNotFoundError(SerialDiscoveryError):
    """Raised when no detected serial port matches a selector."""


class SerialPortAmbiguousError(SerialDiscoveryError):
    """Raised when a selector matches more than one detected serial port."""


@dataclass(frozen=True, slots=True)
class SerialPortInfo:
    """Stable subset of pyserial's platform-specific ``ListPortInfo``."""

    device: str
    name: str | None = None
    description: str | None = None
    hwid: str | None = None
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    location: str | None = None
    interface: str | None = None

    @classmethod
    def from_pyserial(cls, value: Any) -> "SerialPortInfo":
        """Copy a pyserial port record without retaining OS-specific objects."""
        device = _optional_text(getattr(value, "device", None))
        if not device:
            raise SerialDiscoveryError(
                f"pyserial returned a port without a device name: {value!r}"
            )
        return cls(
            device=device,
            name=_optional_text(getattr(value, "name", None)),
            description=_optional_text(getattr(value, "description", None)),
            hwid=_optional_text(getattr(value, "hwid", None)),
            vid=_optional_usb_id(getattr(value, "vid", None), "vid"),
            pid=_optional_usb_id(getattr(value, "pid", None), "pid"),
            serial_number=_optional_text(getattr(value, "serial_number", None)),
            manufacturer=_optional_text(getattr(value, "manufacturer", None)),
            product=_optional_text(getattr(value, "product", None)),
            location=_optional_text(getattr(value, "location", None)),
            interface=_optional_text(getattr(value, "interface", None)),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible metadata for logs or a diagnostics endpoint."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SerialPortSelector:
    """Conjunctive selector for one serial port.

    Every populated field must match.  An explicit ``port`` is therefore both
    a selector and, when combined with USB identity, a guard against a device
    being replaced on that port.
    """

    port: str | None = None
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    location: str | None = None
    hwid: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "port", _optional_text(self.port))
        object.__setattr__(self, "vid", _optional_usb_id(self.vid, "vid"))
        object.__setattr__(self, "pid", _optional_usb_id(self.pid, "pid"))
        for field_name in _TEXT_IDENTITY_FIELDS:
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name)),
            )
        if not self.criteria:
            raise InvalidSerialPortSelector(
                "Serial-port selection requires an explicit port or at least "
                "one USB identity field."
            )

    @property
    def criteria(self) -> dict[str, str | int]:
        values = {
            "port": self.port,
            **{field: getattr(self, field) for field in _IDENTITY_FIELDS},
        }
        return {key: value for key, value in values.items() if value is not None}

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        identity_key: str = "port_identity",
    ) -> "SerialPortSelector":
        """Build a selector from a sensor config without confusing location labels.

        USB identity fields intentionally live under ``port_identity`` because
        sensor configs already use top-level ``location`` for installation
        metadata.  The explicit top-level ``port`` remains compatible with the
        current T-10A and JETI configuration.
        """
        raw_port = config.get("port")
        port = None if _is_auto_port(raw_port) else raw_port
        raw_identity = config.get(identity_key, {})
        if raw_identity is None:
            raw_identity = {}
        if not isinstance(raw_identity, Mapping):
            raise InvalidSerialPortSelector(
                f"{identity_key} must be an object containing USB identity fields."
            )

        unknown = sorted(set(raw_identity) - set(_IDENTITY_FIELDS))
        if unknown:
            supported = ", ".join(_IDENTITY_FIELDS)
            raise InvalidSerialPortSelector(
                f"Unsupported {identity_key} field(s): {', '.join(unknown)}. "
                f"Supported fields: {supported}."
            )

        return cls(
            port=port,
            **{field: raw_identity.get(field) for field in _IDENTITY_FIELDS},
        )

    def mismatch_reasons(
        self,
        candidate: SerialPortInfo,
        *,
        platform_name: str | None = None,
    ) -> tuple[str, ...]:
        """Explain why a candidate does not match this selector."""
        reasons: list[str] = []
        if self.port is not None and not _same_device(
            self.port,
            candidate.device,
            platform_name=platform_name,
        ):
            reasons.append(f"port is {candidate.device!r}, expected {self.port!r}")

        for field_name in ("vid", "pid"):
            expected = getattr(self, field_name)
            actual = getattr(candidate, field_name)
            if expected is not None and expected != actual:
                reasons.append(
                    f"{field_name} is {_format_usb_id(actual)}, "
                    f"expected {_format_usb_id(expected)}"
                )

        for field_name in _TEXT_IDENTITY_FIELDS:
            expected = getattr(self, field_name)
            actual = getattr(candidate, field_name)
            if expected is not None and not _same_text(expected, actual):
                reasons.append(
                    f"{field_name} is {actual!r}, expected {expected!r}"
                )
        return tuple(reasons)

    def matches(
        self,
        candidate: SerialPortInfo,
        *,
        platform_name: str | None = None,
    ) -> bool:
        return not self.mismatch_reasons(
            candidate,
            platform_name=platform_name,
        )

    def describe(self) -> str:
        parts: list[str] = []
        for key, value in self.criteria.items():
            if key in {"vid", "pid"}:
                parts.append(f"{key}={_format_usb_id(int(value))}")
            else:
                parts.append(f"{key}={value!r}")
        return ", ".join(parts)


PortProvider = Callable[[], Iterable[Any]]


def enumerate_serial_ports(
    *,
    port_provider: PortProvider | None = None,
) -> tuple[SerialPortInfo, ...]:
    """Return detected ports in deterministic order without opening any port.

    ``pyserial.tools.list_ports`` supports Windows, Linux, macOS, and BSD.  Some
    metadata may be ``None`` on non-USB or non-Windows devices; callers should
    select only on fields guaranteed by their deployment hardware.
    """
    provider = port_provider or _pyserial_port_provider
    try:
        raw_ports = provider()
        ports = tuple(SerialPortInfo.from_pyserial(item) for item in raw_ports)
    except SerialDiscoveryError:
        raise
    except Exception as exc:
        raise SerialDiscoveryError(
            f"Unable to enumerate serial ports on {sys.platform}: {exc}"
        ) from exc
    return tuple(sorted(ports, key=_port_sort_key))


def resolve_serial_port(
    selector: SerialPortSelector | Mapping[str, Any],
    *,
    ports: Sequence[SerialPortInfo] | None = None,
    platform_name: str | None = None,
) -> SerialPortInfo:
    """Resolve exactly one port or raise an error containing diagnostics."""
    if isinstance(selector, Mapping):
        selector = SerialPortSelector.from_config(selector)
    if not isinstance(selector, SerialPortSelector):
        raise TypeError("selector must be SerialPortSelector or a sensor config mapping")

    platform_name = platform_name or sys.platform
    inventory = (
        enumerate_serial_ports()
        if ports is None
        else tuple(sorted(ports, key=_port_sort_key))
    )
    matches = tuple(
        port
        for port in inventory
        if selector.matches(port, platform_name=platform_name)
    )

    if len(matches) == 1:
        return matches[0]

    inventory_text = format_serial_port_inventory(
        inventory,
        platform_name=platform_name,
    )
    if not matches:
        mismatch_text = _format_mismatches(
            selector,
            inventory,
            platform_name=platform_name,
        )
        raise SerialPortNotFoundError(
            f"No serial port matched ({selector.describe()}).\n"
            f"{inventory_text}{mismatch_text}"
        )

    matching_text = "\n".join(f"  - {format_serial_port(p)}" for p in matches)
    raise SerialPortAmbiguousError(
        f"Serial-port selector matched {len(matches)} ports "
        f"({selector.describe()}):\n{matching_text}\n"
        "Add serial_number, location, or an explicit port to port_identity "
        "selection so exactly one device matches."
    )


def format_serial_port(port: SerialPortInfo) -> str:
    """Format all useful identity metadata on one diagnostic line."""
    vid_pid = (
        f"{_format_usb_id(port.vid)}:{_format_usb_id(port.pid)}"
        if port.vid is not None or port.pid is not None
        else "<unknown>"
    )
    details = (
        ("description", port.description),
        ("vid:pid", vid_pid),
        ("serial", port.serial_number),
        ("manufacturer", port.manufacturer),
        ("product", port.product),
        ("location", port.location),
        ("hwid", port.hwid),
    )
    return f"{port.device}: " + ", ".join(
        f"{label}={value if value is not None else '<unknown>'}"
        for label, value in details
    )


def format_serial_port_inventory(
    ports: Sequence[SerialPortInfo],
    *,
    platform_name: str | None = None,
) -> str:
    """Format a complete inventory for startup logs and error messages."""
    platform_name = platform_name or sys.platform
    if not ports:
        return (
            f"Detected serial ports on {platform_name}: <none>. Discovery is "
            "metadata-only and does not open devices."
        )
    lines = "\n".join(f"  - {format_serial_port(port)}" for port in ports)
    return f"Detected serial ports on {platform_name}:\n{lines}"


def _pyserial_port_provider() -> Iterable[Any]:
    return list_ports.comports(include_links=False)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_usb_id(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise InvalidSerialPortSelector(f"{field_name} must be a USB ID, not boolean")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("0x"):
            text = text[2:]
        try:
            # USB IDs are conventionally written as four hexadecimal digits.
            parsed = int(text, 16)
        except ValueError as exc:
            raise InvalidSerialPortSelector(
                f"{field_name} must be an integer or hexadecimal USB ID, got {value!r}"
            ) from exc
    else:
        raise InvalidSerialPortSelector(
            f"{field_name} must be an integer or hexadecimal USB ID, got {value!r}"
        )
    if not 0 <= parsed <= 0xFFFF:
        raise InvalidSerialPortSelector(
            f"{field_name} must be between 0x0000 and 0xFFFF, got {value!r}"
        )
    return parsed


def _is_auto_port(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().casefold() in {"", "auto"}


def _same_text(expected: str, actual: str | None) -> bool:
    return actual is not None and expected.strip().casefold() == actual.strip().casefold()


def _device_key(value: str) -> tuple[str, int | str]:
    match = _COM_PORT_RE.fullmatch(value.strip())
    if match:
        return ("com", int(match.group(1)))
    return ("path", value)


def _same_device(
    expected: str,
    actual: str,
    *,
    platform_name: str | None = None,
) -> bool:
    expected_key = _device_key(expected)
    actual_key = _device_key(actual)
    if expected_key[0] == "com" or actual_key[0] == "com":
        return expected_key == actual_key
    if (platform_name or sys.platform).startswith("win"):
        return expected.casefold() == actual.casefold()
    return expected == actual


def _port_sort_key(port: SerialPortInfo) -> tuple[int, int | str, str]:
    kind, value = _device_key(port.device)
    if kind == "com":
        return (0, value, port.device.casefold())
    return (1, str(value).casefold(), port.device)


def _format_usb_id(value: int | None) -> str:
    return "<unknown>" if value is None else f"0x{value:04X}"


def _format_mismatches(
    selector: SerialPortSelector,
    ports: Sequence[SerialPortInfo],
    *,
    platform_name: str,
) -> str:
    if not ports:
        return ""
    lines = []
    for port in ports:
        reasons = selector.mismatch_reasons(port, platform_name=platform_name)
        lines.append(f"  - {port.device}: {'; '.join(reasons)}")
    return "\nCandidate mismatches:\n" + "\n".join(lines)
