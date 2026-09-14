"""Tests for the 7-dimension confidence scorer per §15.2/§15.3."""

import pytest

from app.confidence.confidence_explainer import DIMENSION_ORDER
from app.confidence.confidence_explainer import WEIGHTS
from app.confidence.confidence_scorer import score


def _full(value: float) -> dict[str, float]:
    return {name: value for name in DIMENSION_ORDER}


class TestConfidenceScorer:
    """6 tests covering formula, structure and input validation."""

    def test_all_ones_score_one(self) -> None:
        """Seven 1.0 dimensions yield a 1.0 score."""
        result = score(_full(1.0))

        assert result["confidence_score"] == pytest.approx(1.0)

    def test_output_matches_section_15_3(self) -> None:
        """Output has confidence_score, 7 dimensions, explanation, flag."""
        result = score(_full(0.5))

        assert result["confidence_score"] == pytest.approx(0.5)
        assert set(result["dimensions"]) == set(DIMENSION_ORDER)
        assert len(result["dimensions"]) == 7
        assert isinstance(result["explanation"], str) and result["explanation"]
        assert result["not_a_probability"] is True

    def test_weighted_formula(self) -> None:
        """A single 1.0 reliability contributes exactly its weight (0.20)."""
        dimensions = _full(0.0)
        dimensions["source_reliability"] = 1.0

        result = score(dimensions)

        assert result["confidence_score"] == pytest.approx(0.20)

    def test_weights_sum_to_one(self) -> None:
        """§15.2 weights sum to exactly 1.0 over the 7 dimensions."""
        assert set(WEIGHTS) == set(DIMENSION_ORDER)
        assert sum(WEIGHTS.values()) == pytest.approx(1.0)

    def test_missing_dimension_raises(self) -> None:
        """A missing dimension fails explicitly."""
        dimensions = _full(0.5)
        del dimensions["evidence_strength"]

        with pytest.raises(ValueError, match="Missing dimensions"):
            score(dimensions)

    def test_out_of_range_and_non_numeric_raise(self) -> None:
        """Dimensions must be numeric within 0..1."""
        bad_high = _full(0.5)
        bad_high["data_quality"] = 1.5
        with pytest.raises(ValueError, match="within 0..1"):
            score(bad_high)

        bad_type = _full(0.5)
        bad_type["data_quality"] = "high"  # type: ignore[dict-item]
        with pytest.raises(ValueError, match="must be numeric"):
            score(bad_type)
