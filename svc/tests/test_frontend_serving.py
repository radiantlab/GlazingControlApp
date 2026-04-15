from pathlib import Path

from fastapi.testclient import TestClient

import main


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_create_app_serves_built_frontend(monkeypatch, tmp_path):
    dist_dir = tmp_path / "dist"
    write_file(
        dist_dir / "index.html",
        "<!doctype html><html><body><div id='root'>Glazing UI</div></body></html>",
    )
    write_file(dist_dir / "assets" / "main.js", "console.log('frontend asset');")

    monkeypatch.setattr(main, "WEB_DIST_DIR", dist_dir)

    with TestClient(main.create_app()) as client:
        index_response = client.get("/")
        assert index_response.status_code == 200
        assert "Glazing UI" in index_response.text

        asset_response = client.get("/assets/main.js")
        assert asset_response.status_code == 200
        assert "frontend asset" in asset_response.text

        spa_response = client.get("/research/dashboard")
        assert spa_response.status_code == 200
        assert "Glazing UI" in spa_response.text

        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"
