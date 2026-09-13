"""Tests for Confidence endpoints per §15 and §32."""

from fastapi.testclient import TestClient

from app.api.v1.confidence.router import set_confidence_scorer
from app.main import app

client = TestClient(app)


def test_confidence_endpoint_not_implemented_by_default() -> None:
    """Ensure GET /v1/confidence/{information_id} returns not_implemented when scorer absent."""
    set_confidence_scorer(None)
    res = client.get("/v1/confidence/INF_01ARZ3NDEKTSV4RRFFQ69G5F10")
    assert res.status_code == 200
    data = res.json()
    assert data == {"status": "not_implemented"}


def test_confidence_matrix_not_implemented_by_default() -> None:
    """Ensure GET /v1/confidence/matrix/{request_id} returns not_implemented when scorer absent."""
    set_confidence_scorer(None)
    res = client.get("/v1/confidence/matrix/REQ_01ARZ3NDEKTSV4RRFFQ69G5F10")
    assert res.status_code == 200
    data = res.json()
    assert data == {"status": "not_implemented"}


def test_confidence_endpoint_with_active_scorer() -> None:
    """Ensure GET /v1/confidence/{information_id} returns score & 7 dimensions when scorer active."""
    class MockScorer:
        def calculate_confidence(self, info_id: str) -> dict:
            return {
                "information_id": info_id,
                "confidence_score": 0.88,
                "dimensions": {
                    "source_reliability": 0.90,
                    "source_freshness": 0.85,
                    "extraction_confidence": 0.95,
                    "data_quality": 0.80,
                    "evidence_strength": 0.90,
                    "cross_source_agreement": 0.85,
                    "methodological_consistency": 0.90,
                },
                "explanation": "Weighted formula per §15.2",
                "not_a_probability": True,
                "status": "ok",
            }

    try:
        set_confidence_scorer(MockScorer())
        info_id = "INF_01ARZ3NDEKTSV4RRFFQ69G5F77"
        res = client.get(f"/v1/confidence/{info_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["information_id"] == info_id
        assert data["confidence_score"] == 0.88
        assert data["not_a_probability"] is True
        assert len(data["dimensions"]) == 7
        assert "source_reliability" in data["dimensions"]
        assert "cross_source_agreement" in data["dimensions"]
    finally:
        set_confidence_scorer(None)


def test_confidence_matrix_with_active_scorer() -> None:
    """Ensure GET /v1/confidence/matrix/{request_id} returns matrix structure when scorer active."""
    class MockScorer:
        def get_matrix(self, req_id: str) -> dict:
            return {
                "request_id": req_id,
                "matrix": [
                    {
                        "information_id": "INF_01ARZ3NDEKTSV4RRFFQ69G5F01",
                        "confidence_score": 0.91,
                        "dimensions": {
                            "source_reliability": 0.95,
                            "source_freshness": 0.90,
                            "extraction_confidence": 0.90,
                            "data_quality": 0.90,
                            "evidence_strength": 0.90,
                            "cross_source_agreement": 0.90,
                            "methodological_consistency": 0.90,
                        },
                        "explanation": "Calculated per §15.2",
                        "not_a_probability": True,
                        "status": "ok",
                    }
                ],
                "average_confidence": 0.91,
                "total_items": 1,
                "status": "ok",
            }

    try:
        set_confidence_scorer(MockScorer())
        req_id = "REQ_01ARZ3NDEKTSV4RRFFQ69G5F99"
        res = client.get(f"/v1/confidence/matrix/{req_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["request_id"] == req_id
        assert data["average_confidence"] == 0.91
        assert len(data["matrix"]) == 1
        assert data["status"] == "ok"
    finally:
        set_confidence_scorer(None)
