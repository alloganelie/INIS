"""Validity quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class ValidityCheck:
    """Flag null values and blank strings as invalid field values."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        invalid = [
            key for key, value in data.items() if value is None or isinstance(value, str) and not value.strip()
        ]
        total = len(data)
        score = 1.0 if total == 0 else (total - len(invalid)) / total
        return quality_result(score, {"field_count": total}, invalid)
