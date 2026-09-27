"""Unit tests for the §14 provenance-completeness check.

Retained information must carry traceable provenance; ``ProvenanceCheck``
refuses anything without it (§0.2, §14).
"""

from __future__ import annotations

import pytest

from app.quality.checks.provenance_check import ProvenanceCheck


@pytest.fixture
def check() -> ProvenanceCheck:
    """Return the stateless check under test."""
    return ProvenanceCheck()


class TestProvenancePresent:
    """§14 — a non-empty provenance mapping is traceable."""

    async def test_source_and_timestamp_provenance(
        self, check: ProvenanceCheck
    ) -> None:
        """The canonical ``source_id`` / ``retrieved_at`` pair is accepted."""
        result = await check.run(
            {
                "provenance": {
                    "source_id": "SRC_01H0000000000000000000000",
                    "retrieved_at": "2026-09-27T00:00:00Z",
                }
            }
        )
        assert result["score"] == 1.0
        assert result["issues"] == []
        assert result["details"]["has_provenance"] is True

    async def test_minimal_provenance_mapping(self, check: ProvenanceCheck) -> None:
        """Any non-empty mapping is enough for this check."""
        assert (await check.run({"provenance": {"trace_id": "TRF_1"}}))["score"] == 1.0


class TestProvenanceMissing:
    """§0.2 — an untraceable record is rejected."""

    async def test_absent_provenance(self, check: ProvenanceCheck) -> None:
        """No ``provenance`` key at all."""
        result = await check.run({"content": "Paris is the capital of France"})
        assert result["score"] == 0.0
        assert result["issues"] == ["provenance is missing"]
        assert result["details"]["has_provenance"] is False

    async def test_empty_provenance_mapping(self, check: ProvenanceCheck) -> None:
        """An empty mapping carries no traceable reference."""
        assert (await check.run({"provenance": {}}))["score"] == 0.0

    @pytest.mark.parametrize("value", ["SRC_1", 42, ["SRC_1"], None])
    async def test_non_mapping_provenance(
        self, check: ProvenanceCheck, value: object
    ) -> None:
        """A provenance that is not a mapping is not usable."""
        result = await check.run({"provenance": value})
        assert result["score"] == 0.0
        assert result["issues"] == ["provenance is missing"]

    async def test_unsupported_target(self, check: ProvenanceCheck) -> None:
        """An unsupported target has no provenance either."""
        assert (await check.run(object()))["score"] == 0.0


class TestResultShape:
    """§13 — the stable ``QualityResult`` contract."""

    async def test_result_keys(self, check: ProvenanceCheck) -> None:
        """Every check returns exactly score/details/issues."""
        result = await check.run({"provenance": {"source_id": "SRC_1"}})
        assert set(result) == {"score", "details", "issues"}

