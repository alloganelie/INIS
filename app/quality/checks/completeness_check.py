"""Completeness quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class CompletenessCheck:
    """Score fields that are present and non-empty."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        required_fields = data.get("required_fields", list(data))
        missing = [
            field
            for field in required_fields
            if not data.get(field) and data.get(field) not in (0, False)
        ]
        total = len(required_fields)
        score = 1.0 if total == 0 else (total - len(missing)) / total
        return quality_result(score, {"required_fields": required_fields}, missing)
