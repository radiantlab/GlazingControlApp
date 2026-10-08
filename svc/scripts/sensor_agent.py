#!/usr/bin/env python3
"""Run the native Windows physical-sensor agent.

Examples, from ``svc``:

    uv run python scripts/sensor_agent.py list-ports
    uv run python scripts/sensor_agent.py once
    uv run python scripts/sensor_agent.py continuous
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv


SVC_DIR = Path(__file__).resolve().parent.parent
if str(SVC_DIR) not in sys.path:
    sys.path.insert(0, str(SVC_DIR))

# The native collector is a production process. Keep the local development
# file as a fallback, then let the compose/production environment override it
# so the API and collector can share one ingestion token. Explicit process
# environment variables retain the highest precedence.
_process_environment = dict(os.environ)
load_dotenv(SVC_DIR / ".env")
load_dotenv(SVC_DIR / ".env.production", override=True)
os.environ.update(_process_environment)

from app.sensors.host_agent import (  # noqa: E402
    HostSensorAgent,
    OutboxSender,
    SQLiteOutbox,
    build_client_specs,
    load_sensor_config,
    serial_port_inventory,
)


def _default_config_path() -> Path:
    configured_file = os.getenv("SENSOR_AGENT_CONFIG")
    if configured_file:
        candidate = Path(configured_file).expanduser()
        return candidate if candidate.is_absolute() else SVC_DIR / candidate
    production_config_dir = os.getenv("SVC_PRODUCTION_CONFIG_DIR")
    if production_config_dir:
        return Path(production_config_dir).expanduser() / "sensors_config.json"
    configured_file = os.getenv("SENSORS_CONFIG_FILE")
    if configured_file:
        candidate = Path(configured_file).expanduser()
        return candidate if candidate.is_absolute() else SVC_DIR / candidate
    config_dir = Path(
        os.getenv("SVC_CONFIG_DIR", str(SVC_DIR / "config" / "production"))
    )
    return config_dir.expanduser() / "sensors_config.json"


def _default_data_dir() -> Path:
    return Path(
        os.getenv(
            "SENSOR_AGENT_DATA_DIR",
            os.getenv(
                "SVC_PRODUCTION_DATA_DIR",
                os.getenv("SVC_DATA_DIR", str(SVC_DIR / "data")),
            ),
        )
    ).expanduser()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect physical sensors on the native Windows host and forward "
            "durable, idempotent events to GlazingControlApp."
        )
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("SENSOR_AGENT_LOG_LEVEL", "INFO"),
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "list-ports",
        help="List serial metadata without opening or probing any device",
    )

    def add_runtime_options(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--config",
            type=Path,
            default=_default_config_path(),
            help="Path to production sensors_config.json",
        )
        command.add_argument(
            "--data-dir",
            type=Path,
            default=_default_data_dir(),
            help="Native host data directory used by JETI file transports",
        )
        command.add_argument(
            "--outbox",
            type=Path,
            default=Path(
                os.getenv(
                    "SENSOR_AGENT_OUTBOX",
                    str(SVC_DIR / "sensor-agent-data" / "outbox.db"),
                )
            ),
            help="Durable agent-only SQLite outbox (never audit.db)",
        )
        command.add_argument(
            "--endpoint",
            default=os.getenv(
                "SENSOR_INGEST_URL",
                "http://127.0.0.1:8000/sensors/ingest",
            ),
        )
        command.add_argument(
            "--token",
            default=os.getenv(
                "SENSOR_INGEST_TOKEN",
                os.getenv("SVC_SENSOR_INGEST_TOKEN", ""),
            ),
            help=(
                "Ingestion token; set SENSOR_INGEST_TOKEN or "
                "SVC_SENSOR_INGEST_TOKEN instead of putting it in command history"
            ),
        )
        command.add_argument(
            "--agent-id",
            default=os.getenv("SENSOR_AGENT_ID", socket.gethostname()),
        )
        command.add_argument(
            "--batch-size",
            type=int,
            default=int(os.getenv("SENSOR_AGENT_BATCH_SIZE", "250")),
        )
        command.add_argument(
            "--log-file",
            type=Path,
            default=Path(
                os.getenv(
                    "SENSOR_AGENT_LOG_FILE",
                    str(SVC_DIR / "sensor-agent-data" / "agent.log"),
                )
            ),
            help="Rotating operational log path",
        )

    add_runtime_options(subparsers.add_parser("once", help="Poll every device once"))
    add_runtime_options(
        subparsers.add_parser(
            "continuous",
            help="Run independent device workers until Ctrl+C or service stop",
        )
    )
    return parser


def _configure_logging(args: argparse.Namespace) -> None:
    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            args.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    ]
    if sys.stderr.isatty():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )


def _runtime(args: argparse.Namespace) -> tuple[HostSensorAgent, SQLiteOutbox, OutboxSender]:
    if args.outbox.resolve(strict=False).name.casefold() == "audit.db":
        raise ValueError("The sensor-agent outbox must not be audit.db")
    if args.batch_size <= 0 or args.batch_size > 1000:
        raise ValueError("--batch-size must be between 1 and 1000")
    config = load_sensor_config(args.config)
    specs = build_client_specs(config, data_dir=args.data_dir)
    outbox = SQLiteOutbox(args.outbox)
    sender = OutboxSender(
        outbox=outbox,
        endpoint=args.endpoint,
        token=args.token,
        batch_size=args.batch_size,
    )
    agent = HostSensorAgent(
        specs=specs,
        outbox=outbox,
        sender=sender,
        agent_id=args.agent_id,
    )
    return agent, outbox, sender


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "list-ports":
        print(json.dumps({"ports": serial_port_inventory()}, indent=2))
        return 0

    _configure_logging(args)
    agent, outbox, sender = _runtime(args)
    if args.command == "once":
        diagnostics = agent.poll_once()
        delivery = sender.deliver_once()
        result = {
            "polls": diagnostics,
            "delivery": {
                "attempted": delivery.attempted,
                "delivered": delivery.delivered,
                "status_code": delivery.status_code,
                "error": delivery.error,
            },
            "pending": outbox.count(),
        }
        print(json.dumps(result, indent=2))
        return 1 if any(item["event"] == "sensor_poll_failed" for item in diagnostics) else 0

    shutdown = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info(
            json.dumps({"event": "shutdown_requested", "signal": signum})
        )
        shutdown.set()

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        candidate = getattr(signal, signal_name, None)
        if candidate is not None:
            signal.signal(candidate, request_shutdown)

    agent.start()
    try:
        shutdown.wait()
    finally:
        agent.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
