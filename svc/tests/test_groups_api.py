from fastapi.testclient import TestClient

from app.routes import get_service
from app.state import load_snapshot
from main import app

client = TestClient(app)


def sync_simulator_snapshot() -> None:
    service = get_service()
    if hasattr(service.backend, "snap"):
        service.backend.snap = load_snapshot()


def test_group_crud_round_trip():
    sync_simulator_snapshot()
    group_id = None

    try:
        create_response = client.post(
            "/groups",
            json={
                "name": "CI Test Group",
                "member_ids": ["P01", "P02", "MISSING"],
                "layout": {
                    "columns": 2,
                    "items": [
                        {"panel_id": "P01", "row": 1, "column": 2},
                        {"panel_id": "P02", "row": 1, "column": 1},
                    ],
                },
            },
        )
        assert create_response.status_code == 201
        created_group = create_response.json()
        group_id = created_group["id"]

        assert created_group["name"] == "CI Test Group"
        assert created_group["member_ids"] == ["P01", "P02"]
        assert created_group["layout"] == {
            "columns": 2,
            "items": [
                {"panel_id": "P01", "row": 1, "column": 2},
                {"panel_id": "P02", "row": 1, "column": 1},
            ],
        }

        update_response = client.patch(
            f"/groups/{group_id}",
            json={
                "name": "Updated CI Test Group",
                "member_ids": ["SK1", "UNKNOWN"],
                "layout": {
                    "columns": 3,
                    "items": [{"panel_id": "SK1", "row": 2, "column": 3}],
                },
            },
        )
        assert update_response.status_code == 200
        updated_group = update_response.json()

        assert updated_group["id"] == group_id
        assert updated_group["name"] == "Updated CI Test Group"
        assert updated_group["member_ids"] == ["SK1"]
        assert updated_group["layout"] == {
            "columns": 3,
            "items": [{"panel_id": "SK1", "row": 2, "column": 3}],
        }

        groups_response = client.get("/groups")
        assert groups_response.status_code == 200
        assert any(
            group["id"] == group_id and group["name"] == "Updated CI Test Group"
            for group in groups_response.json()
        )
    finally:
        if group_id is not None:
            delete_response = client.delete(f"/groups/{group_id}")
            assert delete_response.status_code == 200
            assert delete_response.json() == {"ok": True}

    groups_after_delete = client.get("/groups")
    assert groups_after_delete.status_code == 200
    assert all(group["id"] != group_id for group in groups_after_delete.json())


def test_group_layout_rows_and_dividers_round_trip():
    sync_simulator_snapshot()
    group_id = None

    try:
        create_response = client.post(
            "/groups",
            json={
                "name": "CI Divider Layout Group",
                "member_ids": ["P01", "P02"],
                "layout": {
                    "columns": 2,
                    "rows": 3,
                    "items": [
                        {"panel_id": "P01", "row": 1, "column": 1},
                        {"panel_id": "P02", "row": 1, "column": 2},
                    ],
                    "dividers": {
                        "vertical": [{"row": 1, "column": 1}],
                        "horizontal": [{"row": 1, "column": 1}, {"row": 1, "column": 2}],
                    },
                },
            },
        )
        assert create_response.status_code == 201
        created_group = create_response.json()
        group_id = created_group["id"]

        assert created_group["layout"] == {
            "columns": 2,
            "rows": 3,
            "items": [
                {"panel_id": "P01", "row": 1, "column": 1},
                {"panel_id": "P02", "row": 1, "column": 2},
            ],
            "dividers": {
                "vertical": [{"row": 1, "column": 1}],
                "horizontal": [{"row": 1, "column": 1}, {"row": 1, "column": 2}],
            },
        }
    finally:
        if group_id is not None:
            delete_response = client.delete(f"/groups/{group_id}")
            assert delete_response.status_code == 200
