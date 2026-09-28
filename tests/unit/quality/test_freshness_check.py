"""Unit tests for §13.2 freshness scoring.

``FreshnessCheck`` compares ``updated_at`` against a configurable maximum age
and feeds the §34 ``stale_data_rate`` gauge on every decision.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.quality.checks.freshness_check import FreshnessCheck


def _iso(moment: datetime) -> str:
    """Return an ISO-8601 UTC timestamp with the ``Z`` suffix."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def check() -> FreshnessCheck:
    """Return a check with the documented 30-day window."""
    return FreshnessCheck()


class TestFreshData:
    """§13.2 — data younger than the window scores 1.0."""

    async def test_recent_timestamp_is_fresh(self, check: FreshnessCheck) -> None:
        """A one-day-old record is accepted."""
        target = {"updated_at": _iso(datetime.now(UTC) - timedelta(days=1))}
        result = await check.run(target)
        assert result["score"] == 1.0
        assert result["issues"] == []
        assert result["details"]["age_days"] == 1

    async def test_naive_timestamp_is_treated_as_utc(
        self, check: FreshnessCheck
    ) -> None:
        """A timestamp without timezone is interpreted as UTC (no crash)."""
        naive = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None)
        result = await check.run({"updated_at": naive.isoformat()})
        assert result["score"] == 1.0

    async def test_custom_window_is_honoured(self) -> None:
        """``max_age_days`` is configurable per check instance."""
        check = FreshnessCheck(max_age_days=365)
        target = {"updated_at": _iso(datetime.now(UTC) - timedelta(days=100))}
        assert (await check.run(target))["score"] == 1.0


class TestStaleData:
    """§13.2 — data beyond the window scores 0.0 and is flagged."""

    async def test_old_timestamp_is_stale(self, check: FreshnessCheck) -> None:
        """A 60-day-old record breaches the 30-day window."""
        target = {"updated_at": _iso(datetime.now(UTC) - timedelta(days=60))}
        result = await check.run(target)
        assert result["score"] == 0.0
        assert result["issues"] == ["data is stale"]
        assert result["details"]["age_days"] == 60

    async def test_narrow_window_makes_recent_data_stale(self) -> None:
        """A 0-day window rejects anything older than today."""
        check = FreshnessCheck(max_age_days=0)
        target = {"updated_at": _iso(datetime.now(UTC) - timedelta(days=1))}
        assert (await check.run(target))["score"] == 0.0


class TestRejectedTimestamps:
    """§13.2 — a missing or unparseable timestamp is never "fresh"."""

    async def test_missing_timestamp(self, check: FreshnessCheck) -> None:
        """No ``updated_at`` means freshness cannot be established."""
        result = await check.run({})
        assert result["score"] == 0.0
        assert result["issues"] == ["updated_at is missing"]
        assert result["details"]["updated_at"] is None

    @pytest.mark.parametrize("value", ["not-a-date", "2026-13-45", "hier"])
    async def test_invalid_timestamp(self, check: FreshnessCheck, value: str) -> None:
        """An unparseable timestamp is reported instead of raising."""
        result = await check.run({"updated_at": value})
        assert result["score"] == 0.0
        assert result["issues"] == ["updated_at is invalid"]

    async def test_empty_timestamp_is_missing(self, check: FreshnessCheck) -> None:
        """An empty string is treated as absent, not as an invalid date."""
        result = await check.run({"updated_at": ""})
        assert result["issues"] == ["updated_at is missing"]


class TestMetricsHook:
    """§34 — every freshness decision is observed by the pipeline metrics."""

    async def test_decision_is_recorded_without_failing_the_check(
        self, check: FreshnessCheck
    ) -> None:
        """The check returns a result whether or not the metrics layer is usable."""
        fresh = await check.run({"updated_at": _iso(datetime.now(UTC))})
        stale = await check.run(
            {"updated_at": _iso(datetime.now(UTC) - timedelta(days=400))}
        )
        assert fresh["score"] == 1.0
        assert stale["score"] == 0.0

