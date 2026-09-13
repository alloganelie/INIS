"""Tests for Information Units endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_information_by_id() -> None:
    """Ensure an Information Unit can be retrieved by its INF_ ID."""
    payload = {
        "source_id": "SRC_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "type": "text",
        "content": {"text": "GDP increased by 2.4% in Q3"},
        "provenance": {"method": "table_extraction", "page": 4},
        "data_stage": "raw",
    }
    create_res = client.post("/v1/information", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    info_id = created["information_id"]
    assert info_id.startswith("INF_")
    assert len(info_id) == len("INF_") + 26

    get_res = client.get(f"/v1/information/{info_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["information_id"] == info_id
    assert data["source_id"] == payload["source_id"]
    assert data["content"]["text"] == payload["content"]["text"]
    assert data["provenance"] == payload["provenance"]


def test_get_information_by_source_id() -> None:
    """Ensure GET /v1/information?source_id=X filters information units by source."""
    target_source_id = "SRC_01ARZ3NDEKTSV4RRFFQ69G5FA1"
    other_source_id = "SRC_01ARZ3NDEKTSV4RRFFQ69G5FA2"

    client.post(
        "/v1/information",
        json={
            "source_id": target_source_id,
            "type": "number",
            "content": {"value": 42},
        },
    )
    client.post(
        "/v1/information",
        json={
            "source_id": other_source_id,
            "type": "number",
            "content": {"value": 99},
        },
    )

    res = client.get(f"/v1/information?source_id={target_source_id}")
    assert res.status_code == 200
    data = res.json()
    units = data.get("units", data.get("items", []))
    assert len(units) >= 1
    assert all(u["source_id"] == target_source_id for u in units)


def test_get_information_not_found() -> None:
    """Ensure querying an unknown information ID returns 404."""
    response = client.get("/v1/information/INF_00000000000000000000000000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
