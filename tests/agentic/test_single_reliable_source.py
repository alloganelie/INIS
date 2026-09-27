"""§33.3 scenario 1 — « source fiable unique ».

A single highly-reliable source must still produce a deliverable result: with
all seven §15.2 dimensions at their maximum, the §15.3 confidence score equals
the full weight mass, i.e. the result clears any delivery threshold even
though only one source was consulted.
"""

from __future__ import annotations

import pytest

from app.confidence.confidence_explainer import DIMENSION_ORDER, WEIGHTS
from app.confidence.confidence_scorer import score


def test_single_reliable_source_yields_maximum_confidence() -> None:
    """All dimensions trusted → confidence equals the full §15.2 weight mass."""
    result = score({name: 1.0 for name in DIMENSION_ORDER})
    expected = sum(WEIGHTS[name] for name in DIMENSION_ORDER)
    assert result["confidence_score"] == pytest.approx(expected)
    assert result["not_a_probability"] is True
    assert result["explanation"]


def test_single_weak_source_is_not_dressed_up_as_confident() -> None:
    """One unreliable source stays visibly low-confidence (§0.2 honesty)."""
    result = score({name: 0.1 for name in DIMENSION_ORDER})
    assert result["confidence_score"] < 0.5
