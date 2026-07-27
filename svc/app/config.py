from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Raised when runtime configuration is missing or unsafe."""


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


def _resolve_path(raw_value: str, *, base: Path) -> Path:
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


@dataclass(frozen=True)
class Settings:
    environment: Environment
    svc_dir: Path
    data_dir: Path
    config_dir: Path
    database_file: Path
    panels_file: Path
    panels_config_file: Path
    panels_state_file: Path
    sensors_config_file: Path
    routines_dir: Path
    min_dwell_seconds: int
    halio_api_url: str
    halio_site_id: str
    halio_api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        svc_dir = Path(__file__).resolve().parent.parent

        legacy_mode = os.getenv("SVC_MODE", "").strip()
        if legacy_mode:
            raise ConfigurationError(
                "SVC_MODE is no longer supported; set "
                "SVC_ENVIRONMENT=development or SVC_ENVIRONMENT=production"
            )

        raw_environment = os.getenv("SVC_ENVIRONMENT", "").strip().lower()
        if not raw_environment:
            raise ConfigurationError(
                "SVC_ENVIRONMENT is required and must be development or production"
            )
        try:
            environment = Environment(raw_environment)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported SVC_ENVIRONMENT={raw_environment!r}; "
                "expected development or production"
            ) from exc

        raw_data_dir = os.getenv("SVC_DATA_DIR", "").strip()
        if not raw_data_dir:
            if environment is Environment.PRODUCTION:
                raise ConfigurationError(
                    "SVC_DATA_DIR is required in production and must point at the "
                    "mounted persistent data directory"
                )
            raw_data_dir = ".runtime/development"
        data_dir = _resolve_path(raw_data_dir, base=svc_dir)

        raw_config_dir = os.getenv("SVC_CONFIG_DIR", "").strip()
        if not raw_config_dir:
            if environment is Environment.PRODUCTION:
                raise ConfigurationError(
                    "SVC_CONFIG_DIR is required in production and must point at the "
                    "read-only mounted production configuration"
                )
            raw_config_dir = "config/development"
        config_dir = _resolve_path(raw_config_dir, base=svc_dir)

        if _paths_overlap(data_dir, config_dir):
            raise ConfigurationError(
                "SVC_DATA_DIR and SVC_CONFIG_DIR must be separate directories "
                f"(got {data_dir} and {config_dir})"
            )

        try:
            min_dwell_seconds = int(os.getenv("SVC_MIN_DWELL_SECONDS", "20"))
        except ValueError as exc:
            raise ConfigurationError("SVC_MIN_DWELL_SECONDS must be an integer") from exc
        if min_dwell_seconds < 0:
            raise ConfigurationError("SVC_MIN_DWELL_SECONDS must be non-negative")

        halio_api_url = os.getenv("HALIO_API_URL", "").strip()
        halio_site_id = os.getenv("HALIO_SITE_ID", "").strip()
        halio_api_key = os.getenv("HALIO_API_KEY", "").strip()
        if environment is Environment.PRODUCTION:
            missing = [
                name
                for name, value in (
                    ("HALIO_API_URL", halio_api_url),
                    ("HALIO_SITE_ID", halio_site_id),
                    ("HALIO_API_KEY", halio_api_key),
                )
                if not value
            ]
            if missing:
                raise ConfigurationError(
                    "Missing required production setting(s): " + ", ".join(missing)
                )

        return cls(
            environment=environment,
            svc_dir=svc_dir,
            data_dir=data_dir,
            config_dir=config_dir,
            database_file=data_dir / "audit.db",
            panels_file=data_dir / "panels.json",
            panels_config_file=config_dir / "panels_config.json",
            panels_state_file=data_dir / "panels_state.json",
            sensors_config_file=config_dir / "sensors_config.json",
            routines_dir=data_dir / "routines",
            min_dwell_seconds=min_dwell_seconds,
            halio_api_url=halio_api_url,
            halio_site_id=halio_site_id,
            halio_api_key=halio_api_key,
        )


SETTINGS = Settings.from_env()

# Module-level aliases keep storage code straightforward and make individual paths
# easy to replace in focused unit tests.
ENVIRONMENT = SETTINGS.environment
IS_DEVELOPMENT = ENVIRONMENT is Environment.DEVELOPMENT
IS_PRODUCTION = ENVIRONMENT is Environment.PRODUCTION
MIN_DWELL_SECONDS = SETTINGS.min_dwell_seconds
DATA_DIR = str(SETTINGS.data_dir)
CONFIG_DIR = str(SETTINGS.config_dir)
PANELS_FILE = str(SETTINGS.panels_file)
PANELS_CONFIG_FILE = str(SETTINGS.panels_config_file)
PANELS_STATE_FILE = str(SETTINGS.panels_state_file)
SENSORS_CONFIG_FILE = str(SETTINGS.sensors_config_file)
AUDIT_DB_FILE = str(SETTINGS.database_file)
ROUTINES_DIR = str(SETTINGS.routines_dir)
HALIO_API_URL = SETTINGS.halio_api_url
HALIO_SITE_ID = SETTINGS.halio_site_id
HALIO_API_KEY = SETTINGS.halio_api_key


def validate_runtime_configuration() -> None:
    """Validate required runtime/config files before database initialization."""
    if IS_PRODUCTION:
        database_file = Path(AUDIT_DB_FILE)
        if not database_file.is_file():
            raise ConfigurationError(
                "Production database does not exist at "
                f"{database_file}; refusing to create an empty replacement"
            )
        return
    config_file = Path(PANELS_CONFIG_FILE)
    if not config_file.is_file():
        raise ConfigurationError(
            f"Development panel configuration does not exist: {config_file}"
        )
    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"Development panel configuration is invalid: {config_file}: {exc}"
        ) from exc
    panels = payload.get("panels") if isinstance(payload, dict) else None
    if not isinstance(panels, dict) or not panels:
        raise ConfigurationError(
            "Development panel configuration must contain a non-empty panels object"
        )
