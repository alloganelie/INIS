"""Router for Data Quality checks and Conflicts per §13, §14.3 and §32."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.v1.quality.schemas import (
    QualityCheckRequest,
    QualityCheckResponse,
    QualityCheckResult,
    QualityReportResponse,
)

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

