"""Temporal consistency quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class TemporalConsistencyCheck:
    """Check that a supplied start timestamp does not follow its end timestamp."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        period = data.get("time", data)
        start = period.get("start") if isinstance(period, dict) else None
        end = period.get("end") if isinstance(period, dict) else None
        issues = ["start follows end"] if start and end and start > end else []
        return quality_result(1.0 if not issues else 0.0, {"start": start, "end": end}, issues)
