"""Freshness quality check."""

from datetime import UTC, datetime, timedelta
from typing import Any

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
        age = datetime.now(UTC) - parsed.astimezone(UTC)
        return quality_result(1.0 if age <= self._max_age else 0.0, {"age_days": age.days}, [] if age <= self._max_age else ["data is stale"])
