"""Conflict detection and resolution module per INIS §14.4."""

from app.domain.entities.conflict import Conflict
from app.quality.conflict.conflict_classifier import classify_difference
from app.quality.conflict.conflict_detector import detect_conflicts
from app.quality.conflict.conflict_resolver import resolve
from app.quality.conflict.conflict_severity import assess_severity

__all__ = [
    "Conflict",
    "detect_conflicts",
    "classify_difference",
    "assess_severity",
    "resolve",
]
