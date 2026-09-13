"""Tests for GET /v1/requests/{id}/progress per §41.1."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_request() -> str:
    """Helper: create a request and return its request_id."""
    res = client.post(
        "/v1/requests",
        json={"objective": "Analyse economic indicators", "request_type": "research"},
    )
    assert res.status_code == 201
    return res.json()["request_id"]


def test_progress_returns_valid_schema() -> None:
    """Ensure GET /v1/requests/{id}/progress returns the expected fields."""
    req_id = _create_request()
    res = client.get(f"/v1/requests/{req_id}/progress")
    assert res.status_code == 200
    data = res.json()
    assert "steps_total" in data
    assert "steps_done" in data
    assert "current_step" in data
    assert "partial_findings_available" in data
    assert isinstance(data["steps_total"], int)
    assert isinstance(data["steps_done"], int)
    assert isinstance(data["current_step"], str)
    assert isinstance(data["partial_findings_available"], bool)


def test_progress_values_are_consistent() -> None:
    """Ensure steps_done <= steps_total and current_step is non-empty."""
    req_id = _create_request()
    data = client.get(f"/v1/requests/{req_id}/progress").json()
    assert data["steps_done"] <= data["steps_total"]
    assert data["steps_total"] > 0
    assert len(data["current_step"]) > 0


def test_progress_not_found() -> None:
    """Ensure querying progress for unknown request ID returns 404."""
    res = client.get("/v1/requests/REQ_00000000000000000000000000/progress")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_changelog_returns_expected_structure() -> None:
    """Ensure GET /v1/changelog returns current_version and history."""
    res = client.get("/v1/changelog")
    assert res.status_code == 200
    data = res.json()
    assert "current_version" in data
    assert "history" in data
    assert isinstance(data["history"], list)
    assert len(data["history"]) >= 1
    entry = data["history"][0]
    assert "version" in entry
    assert "date" in entry
    assert "highlights" in entry
    assert isinstance(entry["highlights"], list)


def test_changelog_current_version() -> None:
    """Ensure current_version matches the running API version."""
    res = client.get("/v1/changelog")
    assert res.status_code == 200
    assert res.json()["current_version"] == "0.1.0"
