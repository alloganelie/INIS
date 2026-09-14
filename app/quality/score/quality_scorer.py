"""Quality scoring per INIS §13.3."""

from typing import Any


DEFAULT_WEIGHTS: dict[str, float] = {
    "completeness": 0.15,
    "validity": 0.15,
    "consistency": 0.15,
    "uniqueness": 0.10,
    "type_conformity": 0.10,
    "freshness": 0.15,
    "provenance_completeness": 0.20,
}


def weighted_mean(results: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Calculate weighted mean of quality metrics per INIS §13.3.

    Args:
        results: Dictionary of quality metric names to scores (0-1)
        weights: Optional custom weights, defaults to DEFAULT_WEIGHTS

    Returns:
        Overall quality score (0-1)
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    total_weight = 0.0
    weighted_sum = 0.0

    for metric, weight in weights.items():
        if metric in results:
            score = results[metric]
            weighted_sum += score * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_sum / total_weight


def score(results: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Calculate quality score from check results.

    Args:
        results: Dictionary of quality check results (metric name -> score)
        weights: Optional custom weights, defaults to DEFAULT_WEIGHTS

    Returns:
        Overall quality score (0-1)
    """
    return weighted_mean(results, weights)
