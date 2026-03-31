from app.adapter import RealAdapter
from app.service import ControlService


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_real_group_acceptance_with_unknown_members(monkeypatch):
    monkeypatch.setattr("app.service.MODE", "real")

    class FakeRealAdapter:
        def set_group(self, group_id, level, min_dwell):
            return []

        def list_panels(self):
            return []

        def list_groups(self):
            return []

    monkeypatch.setattr("app.service.RealAdapter", FakeRealAdapter)

    service = ControlService()
    ok, applied, msg = service.set_group_level("halio-group", 55)

    assert ok is True
    assert applied == []
    assert msg == "group updated"


def test_list_groups_uses_group_details_for_member_ids(monkeypatch):
    monkeypatch.setattr("app.adapter.HAS_REQUESTS", True)
    monkeypatch.setattr("app.adapter.HALIO_API_KEY", "test-key")
    monkeypatch.setattr("app.adapter.HALIO_SITE_ID", "test-site")
    monkeypatch.setattr("app.adapter.HALIO_API_URL", "http://halio/api")

    def fake_get(url, headers=None, timeout=10):
        if url == "http://halio/api/sites/test-site/groups":
            return FakeResponse(200, {"results": [{"id": "group-1", "name": "Window A"}]})
        if url == "http://halio/api/sites/test-site/groups/group-1":
            return FakeResponse(
                200,
                {
                    "results": {
                        "id": "group-1",
                        "name": "Window A",
                        "windows": [{"id": "window-1"}],
                    }
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr("app.adapter.requests.get", fake_get)

    adapter = RealAdapter()
    groups = adapter.list_groups()

    assert len(groups) == 1
    assert groups[0].id == "group-1"
    assert groups[0].member_ids == ["window-1"]


def test_panel_uses_existing_single_window_group(monkeypatch):
    monkeypatch.setattr("app.adapter.HAS_REQUESTS", True)
    monkeypatch.setattr("app.adapter.HALIO_API_KEY", "test-key")
    monkeypatch.setattr("app.adapter.HALIO_SITE_ID", "test-site")
    monkeypatch.setattr("app.adapter.HALIO_API_URL", "http://halio/api")

    def fake_get(url, headers=None, timeout=10):
        if url == "http://halio/api/sites/test-site/windows?attributes=1":
            return FakeResponse(
                200,
                {"results": [{"id": "window-1", "name": "DR-1.1"}]},
            )
        if url == "http://halio/api/sites/test-site/windows/window-1/live-tint-data":
            return FakeResponse(200, {"results": {"level": 0}})
        if url == "http://halio/api/sites/test-site/groups":
            return FakeResponse(200, {"results": [{"id": "group-1", "name": "DR-1.1"}]})
        if url == "http://halio/api/sites/test-site/groups/group-1":
            return FakeResponse(
                200,
                {
                    "results": {
                        "id": "group-1",
                        "name": "DR-1.1",
                        "windows": [{"id": "window-1"}],
                    }
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr("app.adapter.requests.get", fake_get)

    adapter = RealAdapter()
    calls = {}

    def fake_send_group_tint(group_id, level, expected_panel_ids=None):
        calls["group_id"] = group_id
        calls["level"] = level
        calls["expected_panel_ids"] = expected_panel_ids
        return ["window-1"]

    monkeypatch.setattr(adapter, "_send_group_tint", fake_send_group_tint)

    assert adapter.set_panel("window-1", 80, 20) is True
    assert calls == {
        "group_id": "group-1",
        "level": 80,
        "expected_panel_ids": ["window-1"],
    }


def test_list_panels_creates_missing_single_window_groups(monkeypatch):
    monkeypatch.setattr("app.adapter.HAS_REQUESTS", True)
    monkeypatch.setattr("app.adapter.HALIO_API_KEY", "test-key")
    monkeypatch.setattr("app.adapter.HALIO_SITE_ID", "test-site")
    monkeypatch.setattr("app.adapter.HALIO_API_URL", "http://halio/api")

    created_payloads = []

    def fake_get(url, headers=None, timeout=10):
        if url == "http://halio/api/sites/test-site/windows?attributes=1":
            return FakeResponse(
                200,
                {"results": [{"id": "window-1", "name": "DR-1.1"}]},
            )
        if url == "http://halio/api/sites/test-site/windows/window-1/live-tint-data":
            return FakeResponse(200, {"results": {"level": 12}})
        if url == "http://halio/api/sites/test-site/groups":
            return FakeResponse(200, {"results": []})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(url, headers=None, json=None, timeout=10):
        if url == "http://halio/api/sites/test-site/groups":
            created_payloads.append(json)
            return FakeResponse(
                201,
                {"results": {"id": "group-1", "name": "DR-1.1"}},
            )
        raise AssertionError(f"Unexpected POST {url}")

    monkeypatch.setattr("app.adapter.requests.get", fake_get)
    monkeypatch.setattr("app.adapter.requests.post", fake_post)

    adapter = RealAdapter()
    panels = adapter.list_panels()

    assert len(panels) == 1
    assert panels[0].id == "window-1"
    assert created_payloads == [
        {"group": {"name": "DR-1.1", "windows": ["window-1"]}}
    ]


def test_create_group_uses_halio_post_shape(monkeypatch):
    monkeypatch.setattr("app.adapter.HAS_REQUESTS", True)
    monkeypatch.setattr("app.adapter.HALIO_API_KEY", "test-key")
    monkeypatch.setattr("app.adapter.HALIO_SITE_ID", "test-site")
    monkeypatch.setattr("app.adapter.HALIO_API_URL", "http://halio/api")

    captured_payloads = []

    def fake_post(url, headers=None, json=None, timeout=10):
        if url == "http://halio/api/sites/test-site/groups":
            captured_payloads.append(json)
            return FakeResponse(
                201,
                {"results": {"id": "group-9", "name": "My Group"}},
            )
        raise AssertionError(f"Unexpected POST {url}")

    def fake_get(url, headers=None, timeout=10):
        if url == "http://halio/api/sites/test-site/groups/group-9":
            return FakeResponse(
                200,
                {
                    "results": {
                        "id": "group-9",
                        "name": "My Group",
                        "windows": [{"id": "window-1"}, {"id": "window-2"}],
                    }
                },
            )
        raise AssertionError(f"Unexpected GET {url}")

    monkeypatch.setattr("app.adapter.requests.post", fake_post)
    monkeypatch.setattr("app.adapter.requests.get", fake_get)

    adapter = RealAdapter()
    group = adapter.create_group("My Group", ["window-1", "window-2"])

    assert captured_payloads == [
        {"group": {"name": "My Group", "windows": ["window-1", "window-2"]}}
    ]
    assert group.id == "group-9"
    assert group.member_ids == ["window-1", "window-2"]
