from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_list_panels_groups():
    r1 = client.get("/panels")
    r2 = client.get("/groups")
    assert r1.status_code == 200
    assert r2.status_code == 200
    panels = r1.json()
    groups = r2.json()
    # 22 total: 20 facade and 2 skylights
    assert len(panels) == 22
    assert any(g["id"] == "G-facade" for g in groups)

def test_set_and_dwell():
    # first change should succeed
    r = client.post("/commands/set-level", json={"target_type": "panel", "target_id": "P01", "level": 40})
    assert r.status_code == 200
    # immediate second change should throttle by dwell guard
    r2 = client.post("/commands/set-level", json={"target_type": "panel", "target_id": "P01", "level": 70})
    assert r2.status_code == 429
