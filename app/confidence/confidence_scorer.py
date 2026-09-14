"""7-dimension confidence scorer (§15.2 formula, §15.3 output).

Pure function over an explicit ``{dimension: 0..1}`` dict: the 7
dimension values are computed upstream (``dimensions/`` modules) and
validated here. The score is a weighted sum — explicitly not a
probability (``not_a_probability: True`` per §15.3).
"""

from __future__ import annotations

from typing import Any

from app.confidence.confidence_explainer import DIMENSION_ORDER
from app.confidence.confidence_explainer import WEIGHTS
from app.confidence.confidence_explainer import explain


def score(dimensions: dict[str, float]) -> dict[str, Any]:
    """Compute the §15.3 explainable confidence output.

    Raises:
        ValueError: If a dimension is missing, non-numeric or out of 0..1.
    """
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions must be a dict of 7 dimension scores")
    missing = [name for name in DIMENSION_ORDER if name not in dimensions]
    if missing:
        raise ValueError(f"Missing dimensions: {missing}")
    values: dict[str, float] = {}
    for name in DIMENSION_ORDER:
        raw = dimensions[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"Dimension {name} must be numeric, got: {raw!r}")
        value = float(raw)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Dimension {name} must be within 0..1, got: {value}")
        values[name] = value
    total = sum(WEIGHTS[name] * values[name] for name in DIMENSION_ORDER)
    return {
        "confidence_score": total,
        "dimensions": values,
        "explanation": explain(values),
        "not_a_probability": True,
    }
