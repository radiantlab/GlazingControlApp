from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    # Verify we're running in simulator mode for tests
    assert r.json()["mode"] == "sim"


def test_list_panels_groups():
    r1 = client.get("/panels")
    r2 = client.get("/groups")
    assert r1.status_code == 200
    assert r2.status_code == 200
    panels = r1.json()
    groups = r2.json()
    # 20 total: 18 facade + 2 skylights
    assert len(panels) == 20
    assert any(g["id"] == "G-facade" for g in groups)


def test_set_and_dwell():
    # First change should succeed (note: takes ~2s due to simulated transition)
    r = client.post(
        "/commands/set-level",
        json={"target_type": "panel", "target_id": "P01", "level": 40},
    )
    assert r.status_code == 200
    # Immediate second change should throttle by dwell guard
    r2 = client.post(
        "/commands/set-level",
        json={"target_type": "panel", "target_id": "P01", "level": 70},
    )
    assert r2.status_code == 429


def test_panel_state_persistence():
    # Set a panel to a specific level
    r1 = client.post(
        "/commands/set-level",
        json={"target_type": "panel", "target_id": "P02", "level": 50},
    )
    assert r1.status_code == 200

    # Verify the level was set
    r2 = client.get("/panels")
    panels = r2.json()
    p02 = next((p for p in panels if p["id"] == "P02"), None)
    assert p02 is not None
    assert p02["level"] == 50


def test_group_tinting():
    # Tint a group should update all members
    r = client.post(
        "/commands/set-level",
        json={"target_type": "group", "target_id": "G-skylights", "level": 30},
    )
    assert r.status_code == 200
    result = r.json()
    assert result["ok"] is True
    # Should have applied to both skylights
    assert len(result["applied_to"]) == 2
    assert "SK1" in result["applied_to"]
    assert "SK2" in result["applied_to"]
