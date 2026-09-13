"""Tests for Evidence, Conflicts, and Metrics endpoints per §32, §34."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_and_get_evidence_by_id() -> None:
    """Ensure an evidence record can be created and retrieved by its EVID_ ID."""
    payload = {
        "claim_id": "CLM_01ARZ3NDEKTSV4RRFFQ69G5F01",
        "source_id": "SRC_01ARZ3NDEKTSV4RRFFQ69G5F01",
        "excerpt": "According to the official audit, the deficit reached 3.1%.",
        "strength": 0.95,
        "epistemic_status": "fact",
    }
    create_res = client.post("/v1/evidence", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    evidence_id = created["evidence_id"]
    assert evidence_id.startswith("EVID_")
    assert len(evidence_id) == len("EVID_") + 26

    get_res = client.get(f"/v1/evidence/{evidence_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["evidence_id"] == evidence_id
    assert data["claim_id"] == payload["claim_id"]
    assert data["source_id"] == payload["source_id"]
    assert data["excerpt"] == payload["excerpt"]
    assert data["strength"] == 0.95

    # 404 on unknown ID
    not_found_res = client.get("/v1/evidence/EVID_00000000000000000000000000")
    assert not_found_res.status_code == 404
    assert "not found" in not_found_res.json()["detail"].lower()


def test_list_evidence_by_claim_id() -> None:
    """Ensure GET /v1/evidence?claim_id=X filters evidence items properly."""
    target_claim = "CLM_01ARZ3NDEKTSV4RRFFQ69G5F99"
    other_claim = "CLM_01ARZ3NDEKTSV4RRFFQ69G5F88"

    client.post(
        "/v1/evidence",
        json={
            "claim_id": target_claim,
            "source_id": "SRC_01ARZ3NDEKTSV4RRFFQ69G5F01",
            "excerpt": "Target claim evidence text",
        },
    )
    client.post(
        "/v1/evidence",
        json={
            "claim_id": other_claim,
            "source_id": "SRC_01ARZ3NDEKTSV4RRFFQ69G5F02",
            "excerpt": "Other claim evidence text",
        },
    )

    res = client.get(f"/v1/evidence?claim_id={target_claim}")
    assert res.status_code == 200
    data = res.json()
    items = data.get("items", data.get("evidence", []))
    assert len(items) >= 1
    assert all(item["claim_id"] == target_claim for item in items)


def test_create_and_get_conflict_by_id() -> None:
    """Ensure a conflict can be recorded and retrieved by its CONFLICT_ ID."""
    payload = {
        "information_a": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA1",
        "information_b": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA2",
        "difference_type": "value",
        "severity": "high",
        "status": "open",
        "description": "Reported inflation numbers differ by 1.2 points.",
    }
    create_res = client.post("/v1/conflicts", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    conflict_id = created["conflict_id"]
    assert conflict_id.startswith("CONFLICT_")
    assert len(conflict_id) == len("CONFLICT_") + 26

    get_res = client.get(f"/v1/conflicts/{conflict_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["conflict_id"] == conflict_id
    assert data["information_a"] == payload["information_a"]
    assert data["information_b"] == payload["information_b"]
    assert data["difference_type"] == "value"
    assert data["severity"] == "high"
    assert data["status"] == "open"

    # 404 on unknown ID
    not_found_res = client.get("/v1/conflicts/CONFLICT_00000000000000000000000000")
    assert not_found_res.status_code == 404
    assert "not found" in not_found_res.json()["detail"].lower()


def test_list_conflicts_by_status() -> None:
    """Ensure GET /v1/conflicts?status=open filters conflicts by status."""
    client.post(
        "/v1/conflicts",
        json={
            "information_a": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA3",
            "information_b": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA4",
            "difference_type": "date",
            "severity": "medium",
            "status": "open",
        },
    )
    client.post(
        "/v1/conflicts",
        json={
            "information_a": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA5",
            "information_b": "INF_01ARZ3NDEKTSV4RRFFQ69G5FA6",
            "difference_type": "methodology",
            "severity": "low",
            "status": "resolved",
        },
    )

    res = client.get("/v1/conflicts?status=open")
    assert res.status_code == 200
    data = res.json()
    items = data.get("items", data.get("conflicts", []))
    assert len(items) >= 1
    assert all(c["status"] == "open" for c in items)


def test_metrics_endpoint() -> None:
    """Ensure GET /v1/metrics returns 200 with status."""
    res = client.get("/v1/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
