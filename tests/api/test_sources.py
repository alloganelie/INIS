"""Tests for Sources endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_source_success() -> None:
    """Ensure a valid Source can be created with a SRC_ ULID."""
    payload = {
        "name": "Official Statistical Office",
        "source_type": "rest_api",
        "url": "https://api.statistics.gov/v1",
        "description": "National open statistics API",
        "trust_level": 0.95,
    }
    response = client.post("/v1/sources", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["source_id"].startswith("SRC_")
    assert len(data["source_id"]) == len("SRC_") + 26
    assert data["name"] == payload["name"]
    assert data["source_type"] == payload["source_type"]
    assert data["status"] == "active"
    assert data["trust_level"] == 0.95


def test_get_source_by_id() -> None:
    """Ensure an existing Source can be retrieved by its ID."""
    payload = {
        "name": "Regulatory Registry",
        "source_type": "postgres",
    }
    create_res = client.post("/v1/sources", json=payload)
    assert create_res.status_code == 201
    source_id = create_res.json()["source_id"]

    get_res = client.get(f"/v1/sources/{source_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["source_id"] == source_id
    assert data["name"] == payload["name"]


def test_get_source_not_found() -> None:
    """Ensure querying an unknown source ID returns 404."""
    response = client.get("/v1/sources/SRC_00000000000000000000000000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_sources() -> None:
    """Ensure GET /v1/sources returns registered sources and supports filtering."""
    src1 = client.post("/v1/sources", json={"name": "Web Crawler Target", "source_type": "web_page"}).json()
    src2 = client.post("/v1/sources", json={"name": "Internal Data Warehouse", "source_type": "postgres"}).json()

    list_res = client.get("/v1/sources")
    assert list_res.status_code == 200
    data = list_res.json()
    assert "sources" in data or "items" in data
    source_ids = [s["source_id"] for s in data.get("sources", data.get("items", []))]
    assert src1["source_id"] in source_ids
    assert src2["source_id"] in source_ids

    # Test filtering by source_type
    filtered_res = client.get("/v1/sources?source_type=web_page")
    assert filtered_res.status_code == 200
    filtered_data = filtered_res.json()
    filtered_types = [s["source_type"] for s in filtered_data.get("sources", filtered_data.get("items", []))]
    assert all(st == "web_page" for st in filtered_types)
