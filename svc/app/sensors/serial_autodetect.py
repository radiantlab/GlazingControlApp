from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from serial.tools import list_ports

logger = logging.getLogger(__name__)

AUTO_PORT_VALUES = {"", "auto", "autodetect", "detect", "*"}


@dataclass(frozen=True)
class SerialPortCandidate:
    device: str
    name: str
    description: str
    hwid: str
    manufacturer: str
    product: str
    serial_number: str
    location: str
    vid: int | None
    pid: int | None


def is_auto_port(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in AUTO_PORT_VALUES


def serial_port_key(port: str) -> str:
    return str(port).strip().casefold()


def _port_sort_key(port: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"COM(\d+)", str(port).strip(), flags=re.IGNORECASE)
    if match:
        return ("com", int(match.group(1)), str(port).casefold())
    return ("other", 0, str(port).casefold())


def _candidate_from_port_info(info: Any) -> SerialPortCandidate:
    return SerialPortCandidate(
        device=str(getattr(info, "device", "") or ""),
        name=str(getattr(info, "name", "") or ""),
        description=str(getattr(info, "description", "") or ""),
        hwid=str(getattr(info, "hwid", "") or ""),
        manufacturer=str(getattr(info, "manufacturer", "") or ""),
        product=str(getattr(info, "product", "") or ""),
        serial_number=str(getattr(info, "serial_number", "") or ""),
        location=str(getattr(info, "location", "") or ""),
        vid=getattr(info, "vid", None),
        pid=getattr(info, "pid", None),
    )


def serial_match_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """
    Pull optional USB/port match hints out of a sensor config.

    String values are treated as case-insensitive containment checks against
    pyserial's port metadata. vid/pid may be decimal integers or hex strings.
    """
    match: dict[str, Any] = {}
    for key in ("serial_match", "port_match"):
        section = config.get(key)
        if isinstance(section, Mapping):
            match.update(section)

    aliases = {
        "serial_number": "serial_number",
        "usb_serial_number": "serial_number",
        "vid": "vid",
        "usb_vid": "vid",
        "pid": "pid",
        "usb_pid": "pid",
        "manufacturer": "manufacturer",
        "product": "product",
        "description": "description",
        "hwid": "hwid",
        "location": "location",
        "device": "device",
        "name": "name",
    }
    for source_key, target_key in aliases.items():
        if source_key in config and target_key not in match:
            match[target_key] = config[source_key]

    return {key: value for key, value in match.items() if value not in (None, "")}


def list_serial_port_candidates(
    *,
    reserved_ports: set[str] | None = None,
    match: Mapping[str, Any] | None = None,
) -> list[SerialPortCandidate]:
    reserved = {serial_port_key(port) for port in reserved_ports or set()}
    candidates = [
        _candidate_from_port_info(info)
        for info in list_ports.comports()
        if str(getattr(info, "device", "") or "").strip()
    ]
    candidates = [
        candidate
        for candidate in candidates
        if serial_port_key(candidate.device) not in reserved
        and _matches_candidate(candidate, match or {})
    ]
    return sorted(candidates, key=lambda candidate: _port_sort_key(candidate.device))


def find_serial_port(
    *,
    sensor_name: str,
    requested_port: Any,
    probe: Callable[[str], bool],
    reserved_ports: set[str] | None = None,
    match: Mapping[str, Any] | None = None,
) -> str | None:
    if not is_auto_port(requested_port):
        return str(requested_port).strip()

    candidates = list_serial_port_candidates(
        reserved_ports=reserved_ports,
        match=match,
    )
    if not candidates:
        logger.warning("Auto-detect %s: no candidate serial ports found", sensor_name)
        return None

    scanned: list[str] = []
    for candidate in candidates:
        scanned.append(candidate.device)
        try:
            if probe(candidate.device):
                logger.info(
                    "Auto-detected %s on %s (%s)",
                    sensor_name,
                    candidate.device,
                    candidate.description or candidate.hwid or "serial port",
                )
                return candidate.device
        except Exception as e:
            logger.debug(
                "Auto-detect %s: probe failed on %s: %s",
                sensor_name,
                candidate.device,
                e,
            )

    logger.warning(
        "Auto-detect %s: no matching device found after scanning %s",
        sensor_name,
        ", ".join(scanned),
    )
    return None


def _matches_candidate(
    candidate: SerialPortCandidate,
    match: Mapping[str, Any],
) -> bool:
    for key, expected in match.items():
        if expected in (None, ""):
            continue
        if key in {"vid", "pid"}:
            actual = getattr(candidate, key)
            try:
                expected_values = _expected_int_values(expected)
            except ValueError as e:
                logger.warning("Ignoring invalid serial port %s match %r: %s", key, expected, e)
                return False
            if actual is None or actual not in expected_values:
                return False
            continue

        if not hasattr(candidate, key):
            logger.warning("Ignoring unknown serial port match key %r", key)
            continue

        actual_text = str(getattr(candidate, key) or "").casefold()
        if not any(str(value).casefold() in actual_text for value in _expected_values(expected)):
            return False

    return True


def _expected_values(expected: Any) -> list[Any]:
    if isinstance(expected, (list, tuple, set)):
        return list(expected)
    return [expected]


def _expected_int_values(expected: Any) -> set[int]:
    values: set[int] = set()
    for value in _expected_values(expected):
        if isinstance(value, int):
            values.add(value)
            continue
        text = str(value).strip()
        base = 16 if text.lower().startswith("0x") else 10
        values.add(int(text, base))
    return values
