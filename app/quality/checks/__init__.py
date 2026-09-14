"""V1 data-quality checks required by INIS section 13."""

from collections.abc import Mapping
from typing import Any, Protocol, TypeAlias

QualityResult: TypeAlias = dict[str, Any]


class QualityCheck(Protocol):
    """Contract shared by all V1 information-quality checks."""

    async def run(self, target: Any) -> QualityResult:
        """Evaluate a target and return its quality result."""
        ...


def target_mapping(target: Any) -> dict[str, Any]:
    """Normalize a dict or Pydantic model for check implementations."""
    if isinstance(target, Mapping):
        return dict(target)
    model_dump = getattr(target, "model_dump", None)
    if callable(model_dump):
        value = model_dump()
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def quality_result(score: float, details: dict[str, Any], issues: list[str]) -> QualityResult:
    """Return the stable QualityResult shape with a bounded score."""
    return {"score": max(0.0, min(1.0, float(score))), "details": details, "issues": issues}


from app.quality.checks.anomaly_check import AnomalyCheck
from app.quality.checks.completeness_check import CompletenessCheck
from app.quality.checks.consistency_check import ConsistencyCheck
from app.quality.checks.cross_source_consistency_check import CrossSourceConsistencyCheck
from app.quality.checks.duplicates_check import DuplicatesCheck
from app.quality.checks.freshness_check import FreshnessCheck
from app.quality.checks.provenance_check import ProvenanceCheck
from app.quality.checks.temporal_consistency_check import TemporalConsistencyCheck
from app.quality.checks.type_conformity_check import TypeConformityCheck
from app.quality.checks.uniqueness_check import UniquenessCheck
from app.quality.checks.validity_check import ValidityCheck

__all__ = [
    "AnomalyCheck",
    "CompletenessCheck",
    "ConsistencyCheck",
    "CrossSourceConsistencyCheck",
    "DuplicatesCheck",
    "FreshnessCheck",
    "ProvenanceCheck",
    "QualityCheck",
    "QualityResult",
    "TemporalConsistencyCheck",
    "TypeConformityCheck",
    "UniquenessCheck",
    "ValidityCheck",
]
