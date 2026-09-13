"""Tests for Quality endpoints per §13, §14.3, and §32."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_post_quality_check_success() -> None:
    """Ensure POST /v1/quality/check executes quality rules on an InformationUnit."""
    payload = {
        "target_id": "INF_01ARZ3NDEKTSV4RRFFQ69G5F99",
        "target_type": "information_unit",
        "checks": ["completeness", "validity", "freshness"],
    }
    res = client.post("/v1/quality/check", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["target_id"] == payload["target_id"]
    assert data["passed"] is True
    assert "overall_score" in data
    assert isinstance(data["overall_score"], float)
    assert len(data["checks"]) == 3
    check_names = [c["check_name"] for c in data["checks"]]
    assert "completeness" in check_names
    assert "validity" in check_names
    assert "freshness" in check_names


def test_get_quality_report_success() -> None:
    """Ensure GET /v1/quality/report/{target_id} returns cached quality report."""
    target_id = "INF_01ARZ3NDEKTSV4RRFFQ69G5F88"
    client.post("/v1/quality/check", json={"target_id": target_id})

    res = client.get(f"/v1/quality/report/{target_id}")
    assert res.status_code == 200
    report = res.json()
    assert report["target_id"] == target_id
    assert "quality_score" in report
    assert "dimensions" in report
    assert "checks" in report
    assert report["status"] == "evaluated"


def test_get_quality_report_not_found() -> None:
    """Ensure GET /v1/quality/report/{target_id} returns 404 for unknown target."""
    res = client.get("/v1/quality/report/INF_00000000000000000000000000")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_conflicts_endpoints_in_quality() -> None:
    """Ensure conflict creation and retrieval work through quality endpoints."""
    payload = {
        "information_a": "INF_01ARZ3NDEKTSV4RRFFQ69G5F11",
        "information_b": "INF_01ARZ3NDEKTSV4RRFFQ69G5F22",
        "difference_type": "scope",
        "severity": "medium",
        "status": "open",
        "description": "Geographical scope differs between Eurostat and OECD.",
    }
    create_res = client.post("/v1/conflicts", json=payload)
    assert create_res.status_code == 201
    conflict = create_res.json()
    conflict_id = conflict["conflict_id"]
    assert conflict_id.startswith("CONFLICT_")

    get_res = client.get(f"/v1/conflicts/{conflict_id}")
    assert get_res.status_code == 200
    assert get_res.json()["conflict_id"] == conflict_id
    assert get_res.json()["difference_type"] == "scope"

    list_res = client.get("/v1/conflicts")
    assert list_res.status_code == 200
    items = list_res.json().get("items", list_res.json().get("conflicts", []))
    assert any(c["conflict_id"] == conflict_id for c in items)
