"""Type-conformity quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class TypeConformityCheck:
    """Compare values with explicit expected Python types when provided."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        expected_types = data.get("expected_types", {})
        values = data.get("data", data)
        issues = [
            f"{field} has type {type(values.get(field)).__name__}, expected {expected.__name__}"
            for field, expected in expected_types.items()
            if field in values and isinstance(expected, type) and not isinstance(values[field], expected)
        ]
        total = len(expected_types)
        score = 1.0 if total == 0 else (total - len(issues)) / total
        return quality_result(score, {"checked_fields": total}, issues)
