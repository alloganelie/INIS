"""§33.3 scenario 3 — « information obsolète ».

Staleness must be explicit and never silently reused: the §13 freshness check
scores an old source at 0 with a ``data is stale`` issue, the §41.5 cache drops
an entry whose source freshness is below the request threshold, and a delivery
backed by nothing but stale material reports §1.3 ``SOURCE_STALE`` instead of
``SUCCESS``. The §15.2 ``source_freshness`` dimension stays low so the
confidence score visibly degrades.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.confidence.confidence_explainer import DIMENSION_ORDER
from app.confidence.confidence_scorer import score
from app.core.statuses import OUTPUT_STATUSES, SOURCE_STALE_STATUS, resolve_delivery_status
from app.quality.checks import FreshnessCheck
from app.storage.cache.cache_store import CacheInvalidationPolicy, CacheStore


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_source_older_than_the_policy_is_flagged_stale() -> None:
    """A 400-day-old source fails the §13 freshness policy explicitly."""
    check = FreshnessCheck(max_age_days=30)

    result = await check.run({"updated_at": _iso(datetime.now(UTC) - timedelta(days=400))})

    assert result["score"] == 0.0
    assert "data is stale" in result["issues"]
    assert result["details"]["age_days"] >= 400


@pytest.mark.asyncio
async def test_recent_source_is_not_flagged() -> None:
    """Control: a 2-day-old source passes the same policy."""
    check = FreshnessCheck(max_age_days=30)

    result = await check.run({"updated_at": _iso(datetime.now(UTC) - timedelta(days=2))})

    assert result["score"] == 1.0
    assert result["issues"] == []


def test_stale_only_material_reports_source_stale() -> None:
    """No finding and only stale material → §1.3 ``SOURCE_STALE``."""
    assert resolve_delivery_status(findings=[], stale_sources=2) == SOURCE_STALE_STATUS
    assert SOURCE_STALE_STATUS in OUTPUT_STATUSES
    # A stale-only answer must never be dressed up as a successful delivery.
    assert resolve_delivery_status(findings=[], stale_sources=2) != "completed"


def test_stale_cache_entry_is_never_reused() -> None:
    """§41.5: below-threshold ``source_freshness`` → the entry is dropped."""
    store = CacheStore(CacheInvalidationPolicy(freshness_threshold_hours=24))
    store.set(
        "web_search",
        "inflation 2020",
        value={"results": ["stale"]},
        source_freshness=datetime.now(UTC) - timedelta(hours=100),
        source_id="SRC_OLD",
    )

    assert store.get("web_search", "inflation 2020") is None
    assert store.stale_rejections == 1
    assert store.stats()["stale_rejections"] == 1


def test_low_source_freshness_keeps_confidence_low() -> None:
    """§15.2: a low ``source_freshness`` dimension visibly lowers the score."""
    dims = {name: 1.0 for name in DIMENSION_ORDER}
    dims["source_freshness"] = 0.05

    result = score(dims)

    assert result["confidence_score"] < 1.0
    assert result["dimensions"]["source_freshness"] == 0.05
    assert result["not_a_probability"] is True

