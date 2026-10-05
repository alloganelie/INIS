"""Freshness quality check."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.time import utc_now
from app.quality.checks import QualityResult, quality_result, target_mapping


class FreshnessCheck:
    """Score timestamps against a configurable maximum age in days."""

    def __init__(self, max_age_days: int = 30) -> None:
        self._max_age = timedelta(days=max_age_days)

    async def run(self, target: Any) -> QualityResult:
        timestamp = target_mapping(target).get("updated_at")
        if not timestamp:
            return quality_result(0.0, {"updated_at": None}, ["updated_at is missing"])
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        except ValueError:
            return quality_result(0.0, {"updated_at": timestamp}, ["updated_at is invalid"])
        age = utc_now() - parsed.astimezone(UTC)
        stale = age > self._max_age
        # §34 — every freshness decision feeds the stale_data_rate gauge.
        try:
            from app.observability.metrics import record_outcome

            record_outcome("stale_data_rate", failure=stale)
        except Exception:  # noqa: BLE001 - observability never breaks quality
            pass
        return quality_result(1.0 if not stale else 0.0, {"age_days": age.days}, ["data is stale"] if stale else [])
