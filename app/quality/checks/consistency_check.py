"""Internal consistency quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class ConsistencyCheck:
    """Check that paired timestamps are ordered consistently when supplied."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        issues = ["updated_at precedes created_at"] if created_at and updated_at and updated_at < created_at else []
        return quality_result(1.0 if not issues else 0.0, {"created_at": created_at, "updated_at": updated_at}, issues)
