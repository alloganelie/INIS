"""Uniqueness quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class UniquenessCheck:
    """Detect duplicate identifiers in a records or items collection."""

    async def run(self, target: Any) -> QualityResult:
        data = target_mapping(target)
        records = data.get("records", data.get("items", []))
        identifiers = [record.get("id") for record in records if isinstance(record, dict) and record.get("id") is not None]
        duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
        return quality_result(1.0 if not duplicates else 0.0, {"record_count": len(records)}, [f"duplicate id: {value}" for value in duplicates])
