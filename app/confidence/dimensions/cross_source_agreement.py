"""Cross-source agreement dimension (§15.1).

Pure function: averages the per-unit ``agreement`` signals (0..1)
into a single score. An empty unit list means no corroboration at
all (0.0). Without per-unit signals the dimension is neutral (0.5):
fine-grained agreement is computed by the quality/conflict layers.
Accepts dicts and attribute objects.
"""


def _read_agreement(unit: object) -> float | None:
    if isinstance(unit, dict):
        raw = unit.get("agreement", unit.get("cross_source_agreement"))
    else:
        raw = getattr(unit, "agreement", None)
        if raw is None:
            raw = getattr(unit, "cross_source_agreement", None)
    return None if raw is None else max(0.0, min(1.0, float(raw)))


def compute(units: list) -> float:
    """Return the 0..1 cross-source agreement for a list of units."""
    if units is None:
        raise ValueError("units must not be None")
    if len(units) == 0:
        return 0.0
    signals = [_read_agreement(unit) for unit in units]
    signals = [value for value in signals if value is not None]
    if not signals:
        return 0.5
    return sum(signals) / len(signals)
