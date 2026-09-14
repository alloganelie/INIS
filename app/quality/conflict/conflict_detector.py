"""Conflict detection algorithm per INIS §14.4."""

from itertools import combinations

from app.domain.entities.conflict import Conflict
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID
from app.quality.conflict.conflict_classifier import classify_difference
from app.quality.conflict.conflict_severity import assess_severity


def group_by_subject_and_predicate(units: list[InformationUnit]) -> dict[str, list[InformationUnit]]:
    """Group information units by subject and predicate for conflict detection.

    Args:
        units: List of information units to group

    Returns:
        Dictionary mapping subject-predicate keys to lists of units
    """
    groups: dict[str, list[InformationUnit]] = {}

    for unit in units:
        subject = unit.content.get("subject", "unknown")
        predicate = unit.content.get("predicate", "unknown")
        key = f"{subject}:{predicate}"

        if key not in groups:
            groups[key] = []
        groups[key].append(unit)

    return groups


def values_differ(a: InformationUnit, b: InformationUnit) -> bool:
    """Check if two information units have differing values.

    Args:
        a: First information unit
        b: Second information unit

    Returns:
        True if values differ, False otherwise
    """
    a_value = a.content.get("value")
    b_value = b.content.get("value")

    return a_value != b_value


async def detect_conflicts(units: list[InformationUnit]) -> list[Conflict]:
    """Detect conflicts between information units per INIS §14.4.

    Args:
        units: List of information units to check for conflicts

    Returns:
        List of detected conflicts
    """
    conflicts = []
    grouped = group_by_subject_and_predicate(units)

    for group in grouped.values():
        for a, b in combinations(group, 2):
            if values_differ(a, b):
                difference_type = classify_difference(a, b)
                severity = assess_severity(a, b)

                conflict = Conflict(
                    conflict_id=ULID.new("CONFLICT_"),
                    information_a=a.information_id,
                    information_b=b.information_id,
                    difference_type=difference_type,
                    severity=severity,
                    resolution_status="open",
                    resolution_evidence=[]
                )
                conflicts.append(conflict)

    return conflicts
