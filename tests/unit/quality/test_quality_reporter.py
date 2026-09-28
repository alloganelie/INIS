"""Unit tests for QualityReporter per §13.3."""

from unittest.mock import MagicMock

import pytest

from app.quality.score.quality_reporter import _explain_metric, _generate_summary, report


@pytest.mark.asyncio
async def test_report_generates_explicable_summary() -> None:
    target = MagicMock()
    target.information_id = "INF_12345"

    results = {
        "completeness": 0.9,
        "validity": 0.85,
        "consistency": 0.4,
    }

    rep = await report(target, results)

    assert rep["target_id"] == "INF_12345"
    assert rep["overall_score"] > 0.0
    assert len(rep["metric_details"]) == 3
    # Check sorting: highest contribution first
    contributions = [d["contribution"] for d in rep["metric_details"]]
    assert contributions == sorted(contributions, reverse=True)
    assert "summary" in rep


def test_explain_metric_levels() -> None:
    assert "excellent" in _explain_metric("completeness", 0.9)
    assert "good" in _explain_metric("completeness", 0.7)
    assert "fair" in _explain_metric("completeness", 0.5)
    assert "poor" in _explain_metric("completeness", 0.2)


def test_generate_summary_levels() -> None:
    details = [{"metric": "completeness", "score": 0.9}]
    assert "high quality" in _generate_summary(0.85, details)
    assert "low quality" in _generate_summary(0.2, details)
