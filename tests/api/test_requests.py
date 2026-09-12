"""Tests for Information Requests endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_request_success() -> None:
    """Ensure a valid InformationRequest can be created with a REQ_ ULID."""
    payload = {
        "objective": "Analyze cross-domain intelligence data",
        "request_type": "research",
    }
    response = client.post("/v1/requests", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["request_id"].startswith("REQ_")
    assert len(data["request_id"]) == len("REQ_") + 26
    assert data["objective"] == payload["objective"]
    assert data["status"] == "received"


def test_get_request_by_id() -> None:
    """Ensure a created InformationRequest can be retrieved by its ID."""
    payload = {
        "objective": "Retrieve specific provenance records",
        "request_type": "evidence",
    }
    create_res = client.post("/v1/requests", json=payload)
    assert create_res.status_code == 201
    request_id = create_res.json()["request_id"]

    get_res = client.get(f"/v1/requests/{request_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["request_id"] == request_id
    assert data["objective"] == payload["objective"]


def test_get_request_not_found() -> None:
    """Ensure querying an unknown request ID returns 404."""
    response = client.get("/v1/requests/REQ_00000000000000000000000000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_request_validation_error() -> None:
    """Ensure submitting invalid or empty payload returns 422 validation error."""
    response = client.post("/v1/requests", json={})
    assert response.status_code == 422
