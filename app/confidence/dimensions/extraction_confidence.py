"""Extraction confidence dimension (§15.1).

Pure function: returns the information unit's own extraction
confidence clamped to 0..1, or the neutral 0.5 when the unit carries
no confidence signal. Accepts dicts and attribute objects.
"""


def compute(information_unit: object) -> float:
    """Return the 0..1 extraction confidence of an information unit."""
    if information_unit is None:
        raise ValueError("information_unit must not be None")
    if isinstance(information_unit, dict):
        raw = information_unit.get("extraction_confidence", information_unit.get("confidence"))
    else:
        raw = getattr(information_unit, "extraction_confidence", None)
        if raw is None:
            raw = getattr(information_unit, "confidence", None)
    if raw is None:
        return 0.5
    return max(0.0, min(1.0, float(raw)))
