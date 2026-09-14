"""Conflict severity assessment per INIS §14.4."""

from typing import Literal

from app.domain.entities.information_unit import InformationUnit


def assess_severity(a: InformationUnit, b: InformationUnit) -> Literal["low", "medium", "high"]:
    """Assess the severity of a conflict between two information units.

    Args:
        a: First information unit
        b: Second information unit

    Returns:
        Severity level: low, medium, or high
    """
    a_confidence = a.confidence.get("score", 0.0)
    b_confidence = b.confidence.get("score", 0.0)

    a_quality = a.quality.get("score", 0.0)
    b_quality = b.quality.get("score", 0.0)

    min_confidence = min(a_confidence, b_confidence)
    min_quality = min(a_quality, b_quality)

    if min_confidence < 0.3 or min_quality < 0.3:
        return "low"

    if min_confidence < 0.7 or min_quality < 0.7:
        return "medium"

    return "high"
