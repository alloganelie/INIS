"""Pydantic schemas for Quality checks and reports per §13 and §14.3."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.api.v1.conflicts.schemas import (
    ConflictCreate,
    ConflictList,
    ConflictResponse,
)


class QualityCheckRequest(BaseModel):
    """Payload to request a quality check on an Information Unit or target entity."""

    target_id: str = Field(..., description="Target entity ID (e.g. INF_..., DOC_..., DATA_...)")
    target_type: str = Field(default="information_unit", description="Target entity type")
    checks: list[str] = Field(default_factory=list, description="Optional subset of checks to execute")


class QualityCheckResult(BaseModel):
    """Result of an individual quality check rule per §13.2."""

    check_name: str
    passed: bool
    score: float = 1.0
    weight: float = 0.15
    details: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class QualityCheckResponse(BaseModel):
    """Response returned after running quality checks per §13."""

    target_id: str
    passed: bool = True
    overall_score: float = 1.0
    checks: list[QualityCheckResult] = Field(default_factory=list)
    timestamp: str | None = None


class QualityReportResponse(BaseModel):
    """Comprehensive quality evaluation report per §13.3."""

    target_id: str
    quality_score: float = 1.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    checks: list[QualityCheckResult] = Field(default_factory=list)
    status: str = "evaluated"
    generated_at: str | None = None


class ConflictListResponse(ConflictList):
    """List container for conflicts per §14.3."""

    pass


__all__ = [
    "ConflictCreate",
    "ConflictListResponse",
    "ConflictResponse",
    "QualityCheckRequest",
    "QualityCheckResponse",
    "QualityCheckResult",
    "QualityReportResponse",
]
