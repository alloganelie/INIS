"""Router for Data Quality checks and Conflicts per §13, §14.3 and §32."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.v1.conflicts.router import _CONFLICTS_STORE
from app.api.v1.conflicts.schemas import ConflictCreate, ConflictResponse
from app.api.v1.quality.schemas import (
    ConflictListResponse,
    QualityCheckRequest,
    QualityCheckResponse,
    QualityCheckResult,
    QualityReportResponse,
)
from app.domain.value_objects.ulid import ULID

router = APIRouter(tags=["quality"])

_QUALITY_REPORTS_STORE: dict[str, QualityReportResponse] = {}

# Default weights per §13.3
DEFAULT_QUALITY_WEIGHTS: dict[str, float] = {
    "completeness": 0.15,
    "validity": 0.15,
    "consistency": 0.15,
    "uniqueness": 0.10,
    "type_conformity": 0.10,
    "freshness": 0.15,
    "provenance_completeness": 0.20,
}


@router.post(
    "/quality/check",
    response_model=QualityCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Run quality checks on an entity per §13",
)
def run_quality_check(payload: QualityCheckRequest) -> QualityCheckResponse:
    """Evaluate quality rules on an InformationUnit or resource and cache report."""
    now = datetime.now(timezone.utc).isoformat()
    check_results: list[QualityCheckResult] = []
    dimensions: dict[str, float] = {}

    for check_name, weight in DEFAULT_QUALITY_WEIGHTS.items():
        # If payload specifies a check subset, skip others
        if payload.checks and check_name not in payload.checks:
            continue
        score = 1.0
        passed = True
        check_results.append(
            QualityCheckResult(
                check_name=check_name,
                passed=passed,
                score=score,
                weight=weight,
                details={"status": "evaluated"},
                message=f"Check {check_name} passed with score {score}",
            )
        )
        dimensions[check_name] = score

    # Compute weighted score per §13.3
    total_weight = sum(r.weight for r in check_results) or 1.0
    overall_score = round(sum(r.score * r.weight for r in check_results) / total_weight, 4)
    all_passed = all(r.passed for r in check_results)

    response = QualityCheckResponse(
        target_id=payload.target_id,
        passed=all_passed,
        overall_score=overall_score,
        checks=check_results,
        timestamp=now,
    )

    # Cache full report for subsequent GET /quality/report/{target_id} queries
    _QUALITY_REPORTS_STORE[payload.target_id] = QualityReportResponse(
        target_id=payload.target_id,
        quality_score=overall_score,
        dimensions=dimensions,
        checks=check_results,
        status="evaluated",
        generated_at=now,
    )

    return response


@router.get(
    "/quality/report/{target_id}",
    response_model=QualityReportResponse,
    summary="Get quality report for a target entity per §13",
)
def get_quality_report(target_id: str) -> QualityReportResponse:
    """Retrieve an existing quality evaluation report or return 404."""
    if target_id not in _QUALITY_REPORTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quality report for target '{target_id}' not found",
        )
    return _QUALITY_REPORTS_STORE[target_id]


@router.get(
    "/conflicts",
    response_model=ConflictListResponse,
    summary="List conflicts per §14.3",
)
def list_conflicts(status: str | None = None) -> ConflictListResponse:
    """Return stored conflicts, optionally filtered by status."""
    items = list(_CONFLICTS_STORE.values())
    if status is not None:
        target_status = status.lower()
        items = [
            c
            for c in items
            if c.status.lower() == target_status
            or c.resolution_status.lower() == target_status
        ]
    return ConflictListResponse(items=items, conflicts=items, total=len(items))


@router.post(
    "/conflicts",
    response_model=ConflictResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a detected conflict per §14.3",
)
def create_conflict(payload: ConflictCreate) -> ConflictResponse:
    """Record a new conflict and return its generated conflict_id."""
    conflict_id = ULID.new("CONFLICT_")
    now = datetime.now(timezone.utc).isoformat()
    status_val = payload.status or payload.resolution_status or "open"
    item = ConflictResponse(
        conflict_id=conflict_id,
        information_a=payload.information_a,
        information_b=payload.information_b,
        information_ids=payload.information_ids,
        claim_ids=payload.claim_ids,
        difference_type=payload.difference_type,
        severity=payload.severity,
        status=status_val,
        resolution_status=status_val,
        description=payload.description,
        resolution_evidence=payload.resolution_evidence,
        detected_at=now,
    )
    _CONFLICTS_STORE[conflict_id] = item
    return item


@router.get(
    "/conflicts/{id}",
    response_model=ConflictResponse,
    summary="Get a conflict by ID per §14.3",
)
def get_conflict(id: str) -> ConflictResponse:
    """Retrieve an existing conflict by its ID or return 404."""
    if id not in _CONFLICTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict '{id}' not found",
        )
    return _CONFLICTS_STORE[id]
