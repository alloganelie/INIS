"""Methodological consistency dimension (§15.1).

Pure function: averages the per-unit ``consistency`` signals (0..1)
into a single score. An empty unit list scores 0.0. Without per-unit
signals the dimension is neutral (0.5). Accepts dicts and objects.
"""


def _read_consistency(unit: object) -> float | None:
    if isinstance(unit, dict):
        raw = unit.get("consistency", unit.get("methodological_consistency"))
    else:
        raw = getattr(unit, "consistency", None)
        if raw is None:
            raw = getattr(unit, "methodological_consistency", None)
    return None if raw is None else max(0.0, min(1.0, float(raw)))


def compute(units: list) -> float:
    """Return the 0..1 methodological consistency for a list of units."""
    if units is None:
        raise ValueError("units must not be None")
    if len(units) == 0:
        return 0.0
    signals = [_read_consistency(unit) for unit in units]
    signals = [value for value in signals if value is not None]
    if not signals:
        return 0.5
    return sum(signals) / len(signals)
