"""Source reliability dimension (§15.1).

Pure function: returns the source's own ``reliability_score`` (§10.2)
clamped to 0..1, or the neutral 0.5 when the source carries no score.
Accepts dicts and attribute objects (e.g. Codex ``Source`` entity).
"""


def compute(source: object) -> float:
    """Return the 0..1 reliability of a source (§15.1)."""
    if source is None:
        raise ValueError("source must not be None")
    if isinstance(source, dict):
        raw = source.get("reliability_score")
    else:
        raw = getattr(source, "reliability_score", None)
    if raw is None:
        return 0.5
    return max(0.0, min(1.0, float(raw)))
