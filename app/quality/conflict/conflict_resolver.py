"""Conflict resolution per INIS §14.4."""

from typing import Any

from app.quality.conflict.conflict_types import Conflict


async def resolve(conflict: Conflict, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a conflict using provided evidence.

    Args:
        conflict: The conflict to resolve
        evidence: List of evidence items to use for resolution

    Returns:
        Resolution result with status and explanation
    """
    if not evidence:
        return {
            "conflict_id": conflict.conflict_id,
            "resolution_status": "unresolved",
            "explanation": "No evidence provided for resolution"
        }

    evidence_count = len(evidence)
    supporting_a = sum(1 for e in evidence if e.get("supports") == conflict.information_a)
    supporting_b = sum(1 for e in evidence if e.get("supports") == conflict.information_b)

    if supporting_a > supporting_b:
        return {
            "conflict_id": conflict.conflict_id,
            "resolution_status": "resolved",
            "accepted_information": conflict.information_a,
            "explanation": f"Resolved based on {supporting_a}/{evidence_count} evidence items supporting information_a"
        }
    elif supporting_b > supporting_a:
        return {
            "conflict_id": conflict.conflict_id,
            "resolution_status": "resolved",
            "accepted_information": conflict.information_b,
            "explanation": f"Resolved based on {supporting_b}/{evidence_count} evidence items supporting information_b"
        }
    else:
        return {
            "conflict_id": conflict.conflict_id,
            "resolution_status": "unresolved",
            "explanation": f"Evidence is inconclusive: {supporting_a} supporting each side"
        }
