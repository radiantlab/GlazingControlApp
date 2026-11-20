"""Halio health uses mocked HTTP only, with the process kept in development."""

from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from app import routes
from app.config import Environment
from app.service import ControlService
from main import app


def response(status_code=200, payload=None):
    result = Mock(status_code=status_code, text="mock response")
    result.json.return_value = {"results": []} if payload is None else payload
    return result


@pytest.fixture
def halio(monkeypatch):
    monkeypatch.setattr("app.adapter.HALIO_API_URL", "http://halio.invalid/api/v3")
    monkeypatch.setattr("app.adapter.HALIO_SITE_ID", "test-site")
    monkeypatch.setattr("app.adapter.HALIO_API_KEY", "")
    # Select the production adapter without setting SVC_ENVIRONMENT=production
    # or loading any production configuration, hardware, or sensor workers.
    monkeypatch.setattr("app.service.ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(routes, "ENVIRONMENT", Environment.PRODUCTION)
    get = Mock(return_value=response())
    post = Mock(return_value=response(202, {}))
    monkeypatch.setattr("app.adapter.requests.get", get)
    monkeypatch.setattr("app.adapter.requests.post", post)
    service = ControlService()
    monkeypatch.setattr(routes, "svc", service)
    return service.backend, get, post, TestClient(app)


@pytest.mark.parametrize("operation", ["list_panels", "list_groups"])
@pytest.mark.parametrize(
    "failure, reason",
    [
        (requests.exceptions.ConnectionError("Connection refused"), "connection refused"),
        (requests.exceptions.Timeout("read timeout"), "request timed out"),
        (response(503), "HTTP 503"),
        (response(401), "HTTP 401"),
    ],
)
def test_failed_reads_degrade_health_and_recover(halio, monkeypatch, operation, failure, reason):
    adapter, get, _, client = halio
    monkeypatch.setattr("app.adapter.time.time", lambda: 1000.0)
    if isinstance(failure, Exception):
        get.side_effect = failure
    else:
        get.return_value = failure

    assert getattr(adapter, operation)() == []
    health_response = client.get("/health")
    assert health_response.status_code == 200
    health = health_response.json()
    assert health["environment"] == "production"
    assert health["status"] == "degraded"
    assert health["halio_status"] == "degraded"
    assert health["sensor_status"] == "healthy"
    assert health["sensor_errors"] == []
    assert any(f"Halio: {reason} at http://halio.invalid/" in e for e in health["halio_errors"])
    assert adapter.last_success_ts is None
    assert adapter.last_error_ts == 1000.0
    assert reason in adapter.last_error

    monkeypatch.setattr("app.adapter.time.time", lambda: 1001.0)
    get.side_effect = None
    get.return_value = response()
    assert getattr(adapter, operation)() == []
    adapter.list_panels()
    adapter.list_groups()
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["halio_status"] == "healthy"
    assert health["halio_errors"] == []
    assert adapter.last_success_ts == 1001.0
    assert adapter.last_error_ts == 1000.0


def test_empty_reachable_halio_is_healthy(halio):
    adapter, get, _, client = halio
    assert adapter.list_panels() == []
    assert adapter.list_groups() == []
    assert client.get("/health").json()["halio_status"] == "healthy"
    assert client.get("/health").json()["status"] == "ok"
    assert adapter.last_error is None
    assert adapter.last_error_ts is None
    # Health reads recorded outcomes without adding network traffic or writes.
    assert get.call_count == 3


def test_halio_is_unverified_until_a_response_is_observed(halio):
    _, get, _, client = halio
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["halio_errors"] == ["Halio: no successful response received yet"]
    get.assert_not_called()


def test_other_successful_requests_do_not_hide_failures(halio):
    adapter, get, _, client = halio

    def partial_outage(url, **kwargs):
        return response(503 if "/windows?" in url else 200)

    get.side_effect = partial_outage
    assert adapter.list_panels() == []
    assert adapter.list_groups() == []
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["halio_errors"] == [
        "Halio: HTTP 503 at http://halio.invalid/api/v3/sites/test-site/windows"
    ]
    get.side_effect = None
    adapter.list_panels()
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("path", ["groups/group-1", "windows/window-1/live-tint-data"])
def test_detail_failures_are_reported_and_recover(halio, path):
    adapter, get, _, client = halio

    def partial_outage(url, **kwargs):
        if url.endswith(path):
            return response(504)
        if url.endswith("/groups"):
            return response(payload={"results": [{"id": "group-1", "name": "Group"}]})
        return response(payload={"results": [{"id": "window-1", "name": "Window"}]})

    get.side_effect = partial_outage
    adapter._ensured_single_window_groups = True
    adapter.list_panels()
    adapter.list_groups()
    assert any("HTTP 504" in e for e in client.get("/health").json()["halio_errors"])
    get.side_effect = None
    get.return_value = response(payload={"results": {"level": 0, "windows": []}})
    if path.startswith("groups"):
        adapter._get_group_details("group-1")
    else:
        adapter._get_window_state("window-1")
    assert client.get("/health").json()["status"] == "ok"


def test_command_failure_and_recovery_are_reported(halio):
    adapter, _, post, client = halio
    post.side_effect = requests.exceptions.Timeout()
    assert adapter.set_group("group-1", 50, 0) is None
    assert client.get("/health").json()["status"] == "degraded"
    post.side_effect = None
    assert adapter.set_group("group-1", 50, 0) == []
    assert client.get("/health").json()["status"] == "ok"


def test_development_never_reports_halio_errors(halio, monkeypatch):
    adapter, get, _, client = halio
    get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    adapter.list_groups()
    monkeypatch.setattr("app.service.ENVIRONMENT", Environment.DEVELOPMENT)
    monkeypatch.setattr(routes, "ENVIRONMENT", Environment.DEVELOPMENT)
    simulator_service = ControlService()
    monkeypatch.setattr(routes, "svc", simulator_service)
    get.reset_mock()
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["control_source"] == "simulated"
    assert health["halio_status"] == "not_applicable"
    assert health["halio_errors"] == []
    assert simulator_service.list_panels()
    get.assert_not_called()


def test_sensor_and_halio_errors_are_independent(halio, monkeypatch):
    adapter, get, _, client = halio
    monkeypatch.setattr(routes, "get_sensor_health", lambda: ("degraded", ["sensor: failed"]))
    get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    adapter.list_groups()
    health = client.get("/health").json()
    assert health["halio_errors"]
    assert health["sensor_errors"] == ["sensor: failed"]
    get.side_effect = None
    adapter.list_groups()
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["halio_status"] == "healthy"
    assert health["halio_errors"] == []
    assert health["sensor_errors"] == ["sensor: failed"]


def test_diagnostics_omit_credentials_and_query_values(halio):
    adapter, get, _, _ = halio
    # Deliberately fake credentials verify that diagnostics redact URL userinfo.
    adapter.base_url = "http://username:password@halio.invalid/api/v3"  # pragma: allowlist secret
    get.side_effect = requests.exceptions.ConnectionError("refused; private request details")
    adapter.list_panels()
    _, errors = adapter.get_health()
    assert errors == [
        "Halio: connection refused at http://halio.invalid/api/v3/sites/test-site/windows"
    ]
