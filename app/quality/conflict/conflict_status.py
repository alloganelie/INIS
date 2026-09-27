"""Conflict-driven delivery decision per §14.4 and §1.3.

:func:`~app.quality.conflict.conflict_detector.detect_conflicts` answers *what*
contradicts. This module answers *so what*:

* which information units lost cross-source consensus;
* which findings must therefore leave ``findings[]`` (a claim backed by a
  contradicted source is never delivered as a consensus fact);
* which §1.3 status the delivery must carry (``CONFLICTING_SOURCES``);
* the ``conflicts[]`` payload of the §24.1 delivery contract.

Keeping the decision here — instead of inside the pipeline — is what makes
the §33.3 « sources contradictoires » scenario testable without Docker.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.statuses import CONFLICTING_SOURCES_STATUS
from app.core.statuses import resolve_delivery_status
from app.domain.entities.conflict import Conflict
from app.domain.entities.information_unit import InformationUnit
from app.quality.conflict.conflict_detector import detect_conflicts

__all__ = [
    "assess_conflicts",
    "conflict_payload",
    "conflicting_information_ids",
    "consensus_findings",
    "status_for",
]


async def assess_conflicts(units: list[InformationUnit]) -> list[Conflict]:
    """Detect §14.4 conflicts *and* feed the §34 ``conflict_rate`` gauge."""
    conflicts = await detect_conflicts(units)
    try:
        from app.observability.metrics import record_outcome

        record_outcome("conflict_rate", failure=bool(conflicts))
    except Exception:  # noqa: BLE001 - observability must never break quality
        pass
    return conflicts


def conflicting_information_ids(conflicts: Sequence[Conflict]) -> set[str]:
    """Return the information ids that participate in *conflicts*."""
    flags: set[str] = set()
    for conflict in conflicts:
        flags.add(conflict.information_a)
        flags.add(conflict.information_b)
    return flags


def consensus_findings(
    findings: Sequence[Any], conflicts: Sequence[Conflict]
) -> tuple[list[Any], list[Any]]:
    """Split *findings* into ``(kept, dropped)`` per §14.4 consensus rule.

    A finding referencing an information unit involved in an unresolved
    conflict is *dropped*: it is sourced, but not consensually, so delivering
    it as a verified fact would overstate what the sources agree on. Findings
    without an ``information_id`` cannot be matched and are kept.
    """
    flagged = conflicting_information_ids(conflicts)
    kept: list[Any] = []
    dropped: list[Any] = []
    for finding in findings:
        information_id = (
            finding.get("information_id") if isinstance(finding, Mapping) else None
        )
        if information_id and information_id in flagged:
            dropped.append(finding)
        else:
            kept.append(finding)
    return kept, dropped


def conflict_payload(conflicts: Sequence[Conflict]) -> list[dict[str, Any]]:
    """Return the §24.1 ``conflicts[]`` array for the delivery contract."""
    return [conflict.model_dump() for conflict in conflicts]


def status_for(findings: Sequence[Any], conflicts: Sequence[Conflict]) -> str:
    """Return ``CONFLICTING_SOURCES`` when *conflicts* are unresolved (§1.3)."""
    return resolve_delivery_status(findings=findings, conflicts=len(conflicts))


#: Re-exported so callers never have to import the §1.3 module directly.
__all__ += ["CONFLICTING_SOURCES_STATUS"]
