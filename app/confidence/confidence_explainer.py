"""Human-readable explanation of a confidence score (§15.3).

Also owns the canonical §15.2 weights and dimension order, imported
by the scorer — a single dependency direction (scorer → explainer),
no cycle.
"""

from __future__ import annotations

#: §15.2 weights. Sum is exactly 1.0 (covered by unit test).
WEIGHTS: dict[str, float] = {
    "source_reliability": 0.20,
    "source_freshness": 0.10,
    "extraction_confidence": 0.15,
    "data_quality": 0.15,
    "evidence_strength": 0.15,
    "cross_source_agreement": 0.15,
    "methodological_consistency": 0.10,
}

#: §15.1 dimension order (explanation and output rendering).
DIMENSION_ORDER: tuple[str, ...] = tuple(WEIGHTS)


def explain(dimensions: dict[str, float]) -> str:
    """Describe the applied computation rules (§15.3).

    One line per dimension (value, weight, contribution) plus the
    weighted total. Deterministic: follows §15.1 order.
    """
    lines = ["confidence_score = weighted sum of 7 dimensions (§15.2):"]
    total = 0.0
    for name in DIMENSION_ORDER:
        value = float(dimensions[name])
        weight = WEIGHTS[name]
        contribution = weight * value
        total += contribution
        lines.append(
            f"- {name} = {value:.3f} (weight {weight:.2f}) "
            f"-> contribution {contribution:.4f}"
        )
    lines.append(f"total = {total:.4f} (not a probability)")
    return "\n".join(lines)
