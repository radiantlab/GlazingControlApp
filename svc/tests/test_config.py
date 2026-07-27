from __future__ import annotations

import pytest

from app import config
from app.config import ConfigurationError, Environment, Settings


def _clear_environment(monkeypatch) -> None:
    for name in (
        "SVC_MODE",
        "SVC_ENVIRONMENT",
        "SVC_DATA_DIR",
        "SVC_CONFIG_DIR",
        "HALIO_API_URL",
        "HALIO_SITE_ID",
        "HALIO_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_environment_is_required(monkeypatch) -> None:
    _clear_environment(monkeypatch)

    with pytest.raises(ConfigurationError, match="SVC_ENVIRONMENT is required"):
        Settings.from_env()


def test_legacy_mode_is_rejected(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("SVC_MODE", "real")
    monkeypatch.setenv("SVC_ENVIRONMENT", "production")

    with pytest.raises(ConfigurationError, match="SVC_MODE is no longer supported"):
        Settings.from_env()


def test_development_uses_isolated_defaults(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("SVC_ENVIRONMENT", "development")

    settings = Settings.from_env()

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.database_file.name == "audit.db"
    assert settings.data_dir != settings.config_dir


def test_production_requires_explicit_paths_and_halio(monkeypatch, tmp_path) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("SVC_ENVIRONMENT", "production")

    with pytest.raises(ConfigurationError, match="SVC_DATA_DIR is required"):
        Settings.from_env()

    monkeypatch.setenv("SVC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SVC_CONFIG_DIR", str(tmp_path / "config"))
    with pytest.raises(ConfigurationError, match="HALIO_API_URL"):
        Settings.from_env()


def test_config_and_data_directories_cannot_overlap(monkeypatch, tmp_path) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("SVC_ENVIRONMENT", "development")
    monkeypatch.setenv("SVC_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("SVC_CONFIG_DIR", str(tmp_path / "runtime" / "config"))

    with pytest.raises(ConfigurationError, match="must be separate"):
        Settings.from_env()


def test_production_refuses_to_create_missing_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "AUDIT_DB_FILE", str(tmp_path / "missing.db"))

    with pytest.raises(ConfigurationError, match="refusing to create"):
        config.validate_runtime_configuration()


def test_production_and_development_database_paths_are_distinct(
    monkeypatch, tmp_path
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("SVC_ENVIRONMENT", "production")
    monkeypatch.setenv("SVC_DATA_DIR", str(tmp_path / "production-data"))
    monkeypatch.setenv("SVC_CONFIG_DIR", str(tmp_path / "production-config"))
    monkeypatch.setenv("HALIO_API_URL", "http://halio.example/api")
    monkeypatch.setenv("HALIO_SITE_ID", "site-id")
    monkeypatch.setenv("HALIO_API_KEY", "secret")
    production = Settings.from_env()

    monkeypatch.setenv("SVC_ENVIRONMENT", "development")
    monkeypatch.setenv("SVC_DATA_DIR", str(tmp_path / "development-data"))
    monkeypatch.setenv("SVC_CONFIG_DIR", str(tmp_path / "development-config"))
    development = Settings.from_env()

    assert production.database_file != development.database_file
