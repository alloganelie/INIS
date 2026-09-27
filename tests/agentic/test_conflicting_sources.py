"""§33.3 scenario 2 — « sources contradictoires ».

Two sources backing the same subject/predicate with diverging values must be
reported as a §14.4 conflict: the delivery carries a non-empty ``conflicts[]``,
its §1.3 status is ``CONFLICTING_SOURCES`` and the findings backed only by the
contradicted units are dropped — they are sourced, but not *consensually*, so
delivering them as verified facts would overstate the evidence.

Everything here is in-process (no Docker): the conflict detector, the
consensus split and the status rule are the real production code paths.
"""

from __future__ import annotations

import pytest

from app.core.statuses import CONFLICTING_SOURCES_STATUS, OUTPUT_STATUSES
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID
from app.quality.conflict.conflict_status import (
    assess_conflicts,
    conflict_payload,
    consensus_findings,
    status_for,
)


def _unit(value: str, source_id: str) -> InformationUnit:
    """Build a §11 information unit: one subject/predicate, one value."""
    return InformationUnit(
        information_id=ULID.new("INF_"),
        type="number",
        content={"subject": "inflation", "predicate": "annual_rate", "value": value},
        raw_reference={"url": f"https://example.test/{source_id}", "excerpt": value},
        source_id=source_id,
        document_id=ULID.new("DOC_"),
        dataset_id=None,
        location={},
        context={"methodology": "national statistics"},
        language="fr",
        unit="%",
        time={},
        classification={"public": True},
        quality={"score": 0.9},
        confidence={"score": 0.9},
        provenance={"extracted_from": f"https://example.test/{source_id}"},
        versions=[],
        data_stage="derived",
    )


@pytest.mark.asyncio
async def test_contradictory_sources_are_reported_as_a_conflict() -> None:
    """Diverging values on one subject/predicate → a §14.4 conflict."""
    units = [_unit("3.1", "SRC_INSEE"), _unit("4.4", "SRC_OTHER")]

    conflicts = await assess_conflicts(units)
    payload = conflict_payload(conflicts)

    assert conflicts, "two diverging values must be reported, never averaged"
    assert len(payload) == 1
    assert payload[0]["conflict_id"].startswith("CONFLICT_")
    assert payload[0]["information_a"] in {u.information_id for u in units}
    assert payload[0]["difference_type"] == "value"
    assert payload[0]["severity"] in ("low", "medium", "high")
    assert payload[0]["resolution_status"] == "open"


@pytest.mark.asyncio
async def test_no_finding_is_delivered_non_consensually() -> None:
    """A finding backed by a contradicted unit leaves ``findings[]`` (§1.3)."""
    units = [_unit("3.1", "SRC_INSEE"), _unit("4.4", "SRC_OTHER")]
    conflicts = await assess_conflicts(units)
    findings = [
        {"information_id": unit.information_id, "source_id": unit.source_id}
        for unit in units
    ]

    kept, dropped = consensus_findings(findings, conflicts)

    assert kept == [], "a contradicted claim is not a consensus fact"
    assert len(dropped) == 2
    assert status_for(kept, conflicts) == CONFLICTING_SOURCES_STATUS
    assert CONFLICTING_SOURCES_STATUS in OUTPUT_STATUSES


@pytest.mark.asyncio
async def test_agreeing_sources_stay_deliverable() -> None:
    """Control: agreement produces no conflict and the finding survives."""
    units = [_unit("3.1", "SRC_INSEE"), _unit("3.1", "SRC_OTHER")]
    conflicts = await assess_conflicts(units)
    findings = [{"information_id": units[0].information_id, "source_id": "SRC_INSEE"}]

    kept, dropped = consensus_findings(findings, conflicts)

    assert conflicts == []
    assert kept == findings
    assert dropped == []
    assert status_for(kept, conflicts) == "completed"

