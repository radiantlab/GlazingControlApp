from __future__ import annotations

import json

from app.sensors import manager


def test_load_config_resolves_repo_relative_env_path(tmp_path, monkeypatch) -> None:
    repo_dir = tmp_path / "repo"
    svc_dir = repo_dir / "svc"
    data_dir = svc_dir / "data"
    data_dir.mkdir(parents=True)

    config_path = data_dir / "sensors_config.json"
    expected = {"t10a": [], "jeti_spectraval": [], "eko_ms90_plus": []}
    config_path.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.chdir(svc_dir)
    monkeypatch.setattr(manager, "_SVC_DIR", str(svc_dir))
    monkeypatch.setattr(manager, "_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("SENSORS_CONFIG_FILE", "svc/data/sensors_config.json")

    assert manager._load_config() == expected


def test_default_jeti_baudrate_uses_specbos_defaults() -> None:
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2"}) == 115200
    assert manager._default_jeti_baudrate({"label": "Jeti Spectraval 1511"}) == 921600
    assert manager._default_jeti_baudrate({"device_id": "SPECBOS-1211-2", "baudrate": 230400}) == 230400
