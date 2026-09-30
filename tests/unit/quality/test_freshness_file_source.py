"""§13.2/§41.5 — freshness of the sources a delivery carries.

``check_freshness`` existed and was never called: ``sources[].freshness`` stayed
empty and the ``sources.freshness`` column was written as ``NULL``. These tests
cover both source kinds the plan names — a **file** source and a **database**
source — and the rule that matters: an unknown freshness is *stated*, never
assumed fresh (§0.2, §25.1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.quality.source_quality import assess_sources, to_domain_source

FILE_SOURCE = {
    "source_id": "SRC_L5_FILE",
    "source_type": "file",
    "url": "s3://inis-artifacts/documents/REQ_L5/villes.csv",
    "reliability_score": 0.8,
    "freshness": {},
}

DB_SOURCE = {
    "source_id": "SRC_L5_DB",
    "source_type": "database",
    "url": "postgresql://inis_db/public.villes",
    "reliability_score": 0.9,
    "freshness": {},
}


def _ago(days: int) -> str:
    """Return an ISO timestamp *days* in the past."""
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _file_source(**overrides: object) -> dict:
    """Return a fresh file-source entry (``assess_sources`` mutates its input)."""
    return {**FILE_SOURCE, "freshness": {}, **overrides}


def _db_source(**overrides: object) -> dict:
    """Return a fresh database-source entry."""
    return {**DB_SOURCE, "freshness": {}, **overrides}


class TestDeclaredFreshness:
    """A source that declares when it was read is scored on that declaration."""

    @pytest.mark.asyncio
    async def test_a_recent_file_source_is_fresh(self) -> None:
        source = {**FILE_SOURCE, "freshness": {"retrieved_at": _ago(1), "max_age_days": 30}}
        report = await assess_sources([source], [])

        block = report.freshness["SRC_L5_FILE"]
        assert block["score"] == pytest.approx(1.0)
        assert block["max_age_days"] == 30
        assert block["issues"] == []
        assert report.limitations == []

    @pytest.mark.asyncio
    async def test_a_stale_database_source_is_refused(self) -> None:
        source = {**DB_SOURCE, "freshness": {"updated_at": _ago(90), "max_age_days": 30}}
        report = await assess_sources([source], [])

        block = report.freshness["SRC_L5_DB"]
        assert block["score"] == pytest.approx(0.0)
        assert any("stale" in issue for issue in block["issues"])
        assert any("SRC_L5_DB" in limitation for limitation in report.limitations)

    @pytest.mark.asyncio
    async def test_the_evaluated_block_is_written_back_on_the_source(self) -> None:
        """The pipeline persists ``sources[].freshness``: the evaluation lands there."""
        source = {**FILE_SOURCE, "freshness": {"retrieved_at": _ago(1)}}
        await assess_sources([source], [])

        stored = source["freshness"]
        assert stored["score"] == pytest.approx(1.0)
        assert stored["checked_at"].endswith("Z")
        assert "retrieved_at" in stored, "la déclaration d'origine n'est pas écrasée"

    @pytest.mark.asyncio
    async def test_a_declared_age_is_accepted(self) -> None:
        """A source that only declares ``age_days`` is still scorable."""
        source = {**DB_SOURCE, "freshness": {"age_days": 3, "max_age_days": 30}}
        report = await assess_sources([source], [])

        assert report.freshness["SRC_L5_DB"]["score"] == pytest.approx(1.0)


class TestUnknownFreshness:
    """No usable declaration is reported, not assumed recent."""

    @pytest.mark.asyncio
    async def test_a_source_without_metadata_scores_zero_and_says_why(self) -> None:
        report = await assess_sources([_file_source(), _db_source()], [])

        for source_id in ("SRC_L5_FILE", "SRC_L5_DB"):
            block = report.freshness[source_id]
            assert block["score"] == pytest.approx(0.0)
            assert any("freshness timestamp" in issue for issue in block["issues"])
        assert len(report.limitations) == 2
        assert report.assessed_sources == 2

    @pytest.mark.asyncio
    async def test_an_unparsable_timestamp_is_not_fresh(self) -> None:
        source = {**FILE_SOURCE, "freshness": {"retrieved_at": "hier"}}
        report = await assess_sources([source], [])

        assert report.freshness["SRC_L5_FILE"]["score"] == pytest.approx(0.0)
        assert report.freshness["SRC_L5_FILE"]["issues"]

    def test_the_domain_source_is_built_from_the_delivery_entry(self) -> None:
        """The §27 entity is fed by the entry, not by a default."""
        domain = to_domain_source(_file_source())
        assert domain.source_id == "SRC_L5_FILE"
        assert domain.type == "file"
        assert domain.reliability_score == pytest.approx(0.8)
        assert domain.freshness == {}
