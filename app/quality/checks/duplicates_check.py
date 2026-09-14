"""Duplicate-record quality check."""

from collections.abc import Mapping
from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class DuplicatesCheck:
    """Detect repeated records in a Dataset or information-unit collection."""

    async def run(self, target: Any) -> QualityResult:
        """Report repeated mapping values while preserving the standard result shape."""
        data = target_mapping(target)
        records = data.get("records", data.get("items", data.get("information_units", [])))
        normalized_records = [record for record in records if isinstance(record, Mapping)]
        seen: set[tuple[tuple[str, str], ...]] = set()
        duplicate_indexes: list[int] = []

        for index, record in enumerate(normalized_records):
            fingerprint = tuple(sorted((str(key), repr(value)) for key, value in record.items()))
            if fingerprint in seen:
                duplicate_indexes.append(index)
            else:
                seen.add(fingerprint)

        issues = [f"duplicate record at index {index}" for index in duplicate_indexes]
        total = len(normalized_records)
        score = 1.0 if total == 0 else (total - len(duplicate_indexes)) / total
        return quality_result(score, {"record_count": total, "duplicate_count": len(duplicate_indexes)}, issues)
