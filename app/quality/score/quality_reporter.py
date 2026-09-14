"""Quality reporting per INIS §13.3."""

from typing import Any

from app.quality.score.quality_scorer import DEFAULT_WEIGHTS, score


async def report(target: Any, results: dict[str, float], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Generate an explicable quality report for a target.

    Args:
        target: The target being evaluated (InformationUnit, Dataset, etc.)
        results: Dictionary of quality check results (metric name -> score)
        weights: Optional custom weights, defaults to DEFAULT_WEIGHTS

    Returns:
        Explicable quality report with scores and explanations
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    overall_score = score(results, weights)

    metric_details = []
    for metric, weight in weights.items():
        if metric in results:
            metric_score = results[metric]
            contribution = metric_score * weight
            metric_details.append({
                "metric": metric,
                "score": metric_score,
                "weight": weight,
                "contribution": contribution,
                "explanation": _explain_metric(metric, metric_score)
            })

    sorted_details = sorted(metric_details, key=lambda x: x["contribution"], reverse=True)

    return {
        "target_id": getattr(target, "information_id", getattr(target, "dataset_id", "unknown")),
        "overall_score": overall_score,
        "weights_used": weights,
        "metric_details": sorted_details,
        "summary": _generate_summary(overall_score, sorted_details)
    }


def _explain_metric(metric: str, score: float) -> str:
    """Generate explanation for a metric score.

    Args:
        metric: Name of the metric
        score: Score value (0-1)

    Returns:
        Human-readable explanation
    """
    if score >= 0.8:
        level = "excellent"
    elif score >= 0.6:
        level = "good"
    elif score >= 0.4:
        level = "fair"
    else:
        level = "poor"

    explanations = {
        "completeness": f"Data completeness is {level} ({score:.2f})",
        "validity": f"Data validity is {level} ({score:.2f})",
        "consistency": f"Data consistency is {level} ({score:.2f})",
        "uniqueness": f"Data uniqueness is {level} ({score:.2f})",
        "type_conformity": f"Type conformity is {level} ({score:.2f})",
        "freshness": f"Data freshness is {level} ({score:.2f})",
        "provenance_completeness": f"Provenance completeness is {level} ({score:.2f})",
    }

    return explanations.get(metric, f"{metric} score is {level} ({score:.2f})")


def _generate_summary(overall_score: float, details: list[dict[str, Any]]) -> str:
    """Generate a summary of the quality assessment.

    Args:
        overall_score: Overall quality score
        details: Detailed metric information

    Returns:
        Human-readable summary
    """
    if overall_score >= 0.8:
        quality_level = "high quality"
    elif overall_score >= 0.6:
        quality_level = "moderate quality"
    elif overall_score >= 0.4:
        quality_level = "acceptable quality"
    else:
        quality_level = "low quality"

    weak_metrics = [d["metric"] for d in details if d["score"] < 0.5]
    strong_metrics = [d["metric"] for d in details if d["score"] >= 0.8]

    summary_parts = [f"Overall quality is {quality_level} ({overall_score:.2f})."]

    if strong_metrics:
        summary_parts.append(f" Strong areas: {', '.join(strong_metrics)}.")
    if weak_metrics:
        summary_parts.append(f" Areas for improvement: {', '.join(weak_metrics)}.")

    return "".join(summary_parts)
