"""Source freshness dimension (§15.1).

Pure function: linear decay from 1.0 (published now) to 0.0 (a year or
older), or the neutral 0.5 when the source carries no usable date.
Accepts dicts and attribute objects. Dates are ISO 8601 strings.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

_FRESHNESS_WINDOW_DAYS = 365.0

_DATE_FIELDS = ("published_at", "last_modified", "updated_at", "retrieved_at")


def _read_date(source: object) -> str | None:
    if isinstance(source, dict):
        for name in _DATE_FIELDS:
            value = source.get(name)
            if value is not None:
                return str(value)
        return None
    for name in _DATE_FIELDS:
        value = getattr(source, name, None)
        if value is not None:
            return str(value)
    return None


def _parse(date_value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def compute(source: object, now: datetime | None = None) -> float:
    """Return the 0..1 freshness of a source (§15.1)."""
    if source is None:
        raise ValueError("source must not be None")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    raw = _read_date(source)
    if raw is None:
        return 0.5
    published = _parse(raw)
    if published is None:
        return 0.5
    age_days = (moment - published).total_seconds() / 86400.0
    if age_days < 0:
        return 1.0
    return max(0.0, 1.0 - age_days / _FRESHNESS_WINDOW_DAYS)
