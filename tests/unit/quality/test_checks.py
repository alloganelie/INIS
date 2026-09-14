"""Tests for the PHASE-06 V1 quality checks."""

from app.quality.checks import CompletenessCheck
from app.quality.checks import ConsistencyCheck
from app.quality.checks import CrossSourceConsistencyCheck
from app.quality.checks import DuplicatesCheck
from app.quality.checks import ProvenanceCheck
from app.quality.checks import TypeConformityCheck


async def test_completeness_check_reports_missing_required_fields() -> None:
    """Completeness reports required values that are absent."""
    result = await CompletenessCheck().run({"required_fields": ["title", "content"], "title": "Report"})

    assert result["score"] == 0.5
    assert result["issues"] == ["content"]


async def test_consistency_check_detects_reversed_timestamps() -> None:
    """Updated timestamps cannot precede creation timestamps."""
    result = await ConsistencyCheck().run({"created_at": "2026-09-13T10:00:00Z", "updated_at": "2026-09-12T10:00:00Z"})

    assert result["score"] == 0.0
    assert result["issues"]


async def test_type_conformity_check_detects_wrong_type() -> None:
    """Explicit expected types are compared with values."""
    result = await TypeConformityCheck().run({"expected_types": {"count": int}, "data": {"count": "3"}})

    assert result["score"] == 0.0
    assert "count" in result["issues"][0]


async def test_provenance_check_requires_traceability() -> None:
    """Empty provenance metadata is not sufficient for retained data."""
    result = await ProvenanceCheck().run({"provenance": {}})

    assert result["score"] == 0.0
    assert result["issues"] == ["provenance is missing"]


async def test_cross_source_consistency_detects_conflicts() -> None:
    """Different source values are reported as a cross-source issue."""
    result = await CrossSourceConsistencyCheck().run({"sources": [{"value": 10}, {"value": 11}]})

    assert result["score"] == 0.0
    assert result["issues"] == ["sources report conflicting values"]


async def test_duplicates_check_basic() -> None:
    """Exact repeated dataset records lower the duplicates score."""
    result = await DuplicatesCheck().run(
        {"records": [{"id": "INF_1", "value": 1}, {"id": "INF_1", "value": 1}, {"id": "INF_2", "value": 2}]}
    )

    assert result["score"] == 2 / 3
    assert result["details"]["duplicate_count"] == 1
    assert result["issues"] == ["duplicate record at index 1"]
