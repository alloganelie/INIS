"""Cross-source consistency quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class CrossSourceConsistencyCheck:
    """Detect divergent values reported by multiple named sources."""

    async def run(self, target: Any) -> QualityResult:
        sources = target_mapping(target).get("sources", [])
        values = [source.get("value") for source in sources if isinstance(source, dict) and "value" in source]
        distinct_values = {repr(value) for value in values}
        issues = ["sources report conflicting values"] if len(distinct_values) > 1 else []
        return quality_result(1.0 if not issues else 0.0, {"source_count": len(sources)}, issues)
