"""Data quality dimension (§15.1, key ``data_quality``).

Pure function: returns the quality layer's ``quality_score`` clamped
to 0..1, or the neutral 0.5 when the quality result carries no score.
Accepts dicts and attribute objects.

NOTE — module name follows ARCHITECTURE.md (``data_quality_signal.py``);
the §15.1 dimension key stays ``data_quality``.
"""


def compute(quality_result: object) -> float:
    """Return the 0..1 data-quality signal for a quality result."""
    if quality_result is None:
        raise ValueError("quality_result must not be None")
    if isinstance(quality_result, dict):
        raw = quality_result.get("quality_score", quality_result.get("score"))
    else:
        raw = getattr(quality_result, "quality_score", None)
        if raw is None:
            raw = getattr(quality_result, "score", None)
    if raw is None:
        return 0.5
    return max(0.0, min(1.0, float(raw)))
