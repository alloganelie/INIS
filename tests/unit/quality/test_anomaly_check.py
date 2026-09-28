"""Unit tests for §13.2 anomaly detection.

``AnomalyCheck`` flags numeric values further than three standard deviations
from their mean and always returns the stable ``QualityResult`` shape.
"""

from __future__ import annotations

import pytest

from app.quality.checks.anomaly_check import AnomalyCheck


@pytest.fixture
def check() -> AnomalyCheck:
    """Return the stateless check under test."""
    return AnomalyCheck()


class TestNoAnomaly:
    """§13.2 — clean distributions score 1.0 and report no issue."""

    async def test_outlier_free_distribution(self, check: AnomalyCheck) -> None:
        """Values close to their mean are accepted."""
        result = await check.run({"values": [10, 11, 9, 10, 12]})
        assert result["score"] == 1.0
        assert result["issues"] == []
        assert result["details"]["value_count"] == 5

    async def test_fewer_than_two_values_is_not_an_anomaly(
        self, check: AnomalyCheck
    ) -> None:
        """A single (or absent) value has no standard deviation to compare to."""
        for target in ({"values": []}, {"values": [42]}, {}):
            result = await check.run(target)
            assert result["score"] == 1.0
            assert result["issues"] == []

    async def test_constant_distribution_is_not_an_anomaly(
        self, check: AnomalyCheck
    ) -> None:
        """A zero standard deviation would divide by zero; it must not raise."""
        result = await check.run({"values": [5, 5, 5, 5]})
        assert result["score"] == 1.0
        assert result["details"]["mean"] == 5.0


class TestAnomalyDetected:
    """§13.2 — a value beyond 3σ is reported as an anomaly."""

    async def test_outlier_scores_zero_and_is_listed(self, check: AnomalyCheck) -> None:
        """The outlier is named in ``issues`` and the score drops to 0.0."""
        result = await check.run({"values": [1] * 10 + [100]})
        assert result["score"] == 0.0
        assert result["issues"] == ["anomaly: 100"]

    async def test_multiple_outliers_are_all_reported(self, check: AnomalyCheck) -> None:
        """Every anomalous value appears once in the issue list."""
        result = await check.run({"values": [1] * 20 + [100, 100]})
        assert result["issues"] == ["anomaly: 100", "anomaly: 100"]
        assert result["score"] == 0.0


class TestInputNormalization:
    """§13 — non-numeric and Pydantic inputs are handled without crashing."""

    async def test_non_numeric_values_are_ignored(self, check: AnomalyCheck) -> None:
        """Strings inside ``values`` do not contribute to the statistics."""
        result = await check.run({"values": ["n/a", 10, 10, 10]})
        assert result["details"]["value_count"] == 3
        assert result["score"] == 1.0

    async def test_pydantic_model_input(self, check: AnomalyCheck) -> None:
        """A model exposing ``model_dump`` is normalized like a dict."""
        from pydantic import BaseModel

        class Target(BaseModel):
            values: list[float]

        result = await check.run(Target(values=[1.0, 1.0, 1.0]))
        assert result["details"]["value_count"] == 3

    async def test_unsupported_target_yields_empty_stats(
        self, check: AnomalyCheck
    ) -> None:
        """An unsupported target is not an error: it just has no values."""
        result = await check.run(object())
        assert result["score"] == 1.0
        assert result["details"]["value_count"] == 0

    async def test_score_is_bounded(self, check: AnomalyCheck) -> None:
        """``quality_result`` always clamps the score into [0, 1]."""
        result = await check.run({"values": [1, 2, 3]})
        assert 0.0 <= result["score"] <= 1.0

