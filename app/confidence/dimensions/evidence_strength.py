"""Evidence strength dimension (§15.1).

Pure function: returns the evidence's own ``strength`` (Codex
``Evidence`` entity, 0..1) clamped to 0..1, or the neutral 0.5 when
the evidence carries no strength. Accepts dicts and attribute objects.
"""


def compute(evidence: object) -> float:
    """Return the 0..1 strength of an evidence (§15.1)."""
    if evidence is None:
        raise ValueError("evidence must not be None")
    if isinstance(evidence, dict):
        raw = evidence.get("strength")
    else:
        raw = getattr(evidence, "strength", None)
    if raw is None:
        return 0.5
    return max(0.0, min(1.0, float(raw)))
