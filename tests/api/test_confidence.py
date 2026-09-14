"""Tests for Confidence endpoints per SS15 and SS32."""

import sys

import pytest
from fastapi.testclient import TestClient

from app.api.v1.confidence.router import set_confidence_scorer
from app.main import app

client = TestClient(app)

INF_ULID = "INF_01ARZ3NDEKTSV4RRFFQ69G5FAA"
REQ_ULID = "REQ_01ARZ3NDEKTSV4RRFFQ69G5FBB"


# ---------------------------------------------------------------------------
# Happy-path tests (replace the obsolete not_implemented tests)
# ---------------------------------------------------------------------------


def test_confidence_endpoint_returns_score() -> None:
    """GET /v1/confidence/{info_id} returns 200 with score, 7 dimensions and not_a_probability."""

    class MockScorer:
        def calculate_confidence(self, info_id: str) -> dict:
            return {
                "information_id": info_id,
                "confidence_score": 0.87,
                "dimensions": {
                    "source_reliability": 0.90,
                    "source_freshness": 0.85,
                    "extraction_confidence": 0.95,
                    "data_quality": 0.80,
                    "evidence_strength": 0.90,
                    "cross_source_agreement": 0.85,
                    "methodological_consistency": 0.90,
                },
                "not_a_probability": True,
                "status": "ok",
            }

    try:
        set_confidence_scorer(MockScorer())
        res = client.get(f"/v1/confidence/{INF_ULID}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert isinstance(data["confidence_score"], float)
        assert len(data["dimensions"]) == 7
        assert data["not_a_probability"] is True
    finally:
        set_confidence_scorer(None)


def test_confidence_matrix_returns_matrix() -> None:
    """GET /v1/confidence/matrix/{req_id} returns 200 with average_confidence and matrix list."""

    class MockScorer:
        def get_matrix(self, req_id: str) -> dict:
            return {
                "request_id": req_id,
                "matrix": [
                    {
                        "information_id": INF_ULID,
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
        res = client.get(f"/v1/confidence/matrix/{REQ_ULID}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert isinstance(data["average_confidence"], float)
        assert isinstance(data["matrix"], list)
        assert len(data["matrix"]) >= 1
    finally:
        set_confidence_scorer(None)


# ---------------------------------------------------------------------------
# Fallback not_implemented tests (monkeypatch scorer absence)
# ---------------------------------------------------------------------------


def test_confidence_endpoint_fallback_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    """When _get_active_scorer returns None (no scorer), endpoint returns not_implemented."""
    import importlib

    router_mod = sys.modules.get("app.api.v1.confidence.router") or importlib.import_module(
        "app.api.v1.confidence.router"
    )
    monkeypatch.setattr(router_mod, "_get_active_scorer", lambda: None)
    res = client.get(f"/v1/confidence/{INF_ULID}")
    assert res.status_code == 200
    assert res.json() == {"status": "not_implemented"}


def test_confidence_matrix_fallback_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    """When _get_active_scorer returns None (no scorer), matrix endpoint returns not_implemented."""
    import importlib

    router_mod = sys.modules.get("app.api.v1.confidence.router") or importlib.import_module(
        "app.api.v1.confidence.router"
    )
    monkeypatch.setattr(router_mod, "_get_active_scorer", lambda: None)
    res = client.get(f"/v1/confidence/matrix/{REQ_ULID}")
    assert res.status_code == 200
    assert res.json() == {"status": "not_implemented"}


# ---------------------------------------------------------------------------
# Existing active-scorer tests (preserved)
# ---------------------------------------------------------------------------


def test_confidence_endpoint_with_active_scorer() -> None:
    """Ensure GET /v1/confidence/{information_id} returns score and 7 dimensions when scorer active."""

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
                "explanation": "Weighted formula per SS15.2",
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
                        "explanation": "Calculated per SS15.2",
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
