#!/usr/bin/env python3
"""
Read raw T-10A traffic on a serial port (for on-site debugging).

Close the GlazingControlApp backend first so nothing else holds the COM port.

Examples (from svc/):
  uv run python scripts/read_t10a_serial.py COM5
  uv run python scripts/read_t10a_serial.py COM5 --pc-mode-only
"""
from __future__ import annotations

import argparse
import sys
import time

import serial

from app.sensors.t10a_client import T10AClient


def _pc_mode_frame(head: int = 0) -> bytes:
    client = T10AClient.__new__(T10AClient)
    client._head_index_base = 0
    client._body_template = "{head:02d}{cmd}{params}"
    return client._build_frame(head, "54", "1 ")


def _measure_frame(head: int = 0) -> bytes:
    client = T10AClient.__new__(T10AClient)
    client._head_index_base = 0
    client._body_template = "{head:02d}{cmd}{params}"
    return client._build_frame(head, "10", "0200")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Konica Minolta T-10A on a COM port")
    parser.add_argument("port", help="Windows COM port, e.g. COM5")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--head", type=int, default=0, help="Head/adaptor number (0-29)")
    parser.add_argument(
        "--no-xonxoff",
        action="store_true",
        help="Disable software flow control (try if you get no reply)",
    )
    parser.add_argument(
        "--pc-mode-only",
        action="store_true",
        help="Send only PC mode (cmd 54) and exit",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Only listen for unsolicited bytes (no commands sent)",
    )
    args = parser.parse_args()

    print(
        f"Opening {args.port} @ {args.baudrate} 7E1 "
        f"(xonxoff={not args.no_xonxoff}, timeout={args.timeout}s)"
    )
    ser = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        timeout=args.timeout,
        xonxoff=not args.no_xonxoff,
    )
    time.sleep(0.2)

    if args.listen:
        print("Listening… Ctrl+C to stop.")
        try:
            while True:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    print(repr(chunk))
        except KeyboardInterrupt:
            pass
        finally:
            ser.close()
        return 0

    pc_frame = _pc_mode_frame(args.head)
    meas_frame = _measure_frame(args.head)

    def exchange(label: str, tx: bytes, read_len: int) -> None:
        print(f"\n--- {label} ---")
        print("TX:", repr(tx))
        ser.reset_input_buffer()
        ser.write(tx)
        ser.flush()
        time.sleep(0.15)
        rx = ser.read(read_len)
        if len(rx) < read_len:
            extra = ser.read_until(expected=b"\r\n")
            rx = (rx + extra)[: max(read_len, len(rx + extra))]
        print("RX:", repr(rx))
        if not rx:
            print("WARNING: empty reply")

    exchange("PC mode (54)", pc_frame, 14)
    if args.pc_mode_only:
        ser.close()
        return 0

    exchange("Measurement (10)", meas_frame, 32)
    ser.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
