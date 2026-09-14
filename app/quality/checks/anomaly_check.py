"""Numeric anomaly quality check."""

from math import sqrt
from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class AnomalyCheck:
    """Flag values more than three standard deviations from their mean."""

    async def run(self, target: Any) -> QualityResult:
        values = [value for value in target_mapping(target).get("values", []) if isinstance(value, (int, float))]
        if len(values) < 2:
            return quality_result(1.0, {"value_count": len(values)}, [])
        mean = sum(values) / len(values)
        deviation = sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        anomalies = [] if deviation == 0 else [value for value in values if abs(value - mean) / deviation > 3]
        return quality_result(1.0 if not anomalies else 0.0, {"mean": mean, "value_count": len(values)}, [f"anomaly: {value}" for value in anomalies])
