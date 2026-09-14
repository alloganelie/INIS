"""Pydantic schemas for Confidence scores and matrices per §15 and §32."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConfidenceScoreResponse(BaseModel):
    """Explicable confidence score per §15.3."""

    information_id: str | None = None
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Computed aggregate confidence score")
    dimensions: dict[str, float] = Field(
        default_factory=lambda: {
            "source_reliability": 1.0,
            "source_freshness": 1.0,
            "extraction_confidence": 1.0,
            "data_quality": 1.0,
            "evidence_strength": 1.0,
            "cross_source_agreement": 1.0,
            "methodological_consistency": 1.0,
        },
        description="7 explicable confidence dimensions per §15.1",
    )
    explanation: str | None = Field(
        default="Weighted combination of 7 confidence dimensions per §15.2",
        description="Description of computation rules",
    )
    not_a_probability: bool = Field(default=True, description="Strict invariant: confidence is not a probability")
    status: str = "ok"


class ConfidenceMatrixResponse(BaseModel):
    """Confidence matrix for all findings/units within a request per §15."""

    request_id: str = Field(..., description="Target request ID (REQ_...)")
    matrix: list[ConfidenceScoreResponse] = Field(default_factory=list, description="List of confidence scores")
    average_confidence: float = Field(default=1.0, description="Average confidence score across matrix")
    total_items: int = Field(default=0, description="Total scored items")
    status: str = "ok"


__all__ = [
    "ConfidenceMatrixResponse",
    "ConfidenceScoreResponse",
]
