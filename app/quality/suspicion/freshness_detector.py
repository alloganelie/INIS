"""Artificial-freshness detection (§41.7).

Detects *re-dated* content: an old document presented with a recent date.
Two signals (``stated_published_at`` is what the source claims):

* the stated date lies in the future, or
* the stated date is newer than the actual content date by more than the
  tolerance window — the classic re-dating of archived content.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

#: Allowed slack between the stated and actual content dates, in days.
DEFAULT_TOLERANCE_DAYS = 30
#: Allowed slack before a stated date counts as "in the future", in days.
_FUTURE_SLACK = timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC so comparisons never mix offsets."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def detect_freshness_manipulation(
    stated_published_at: datetime | None,
    content_date: datetime | None = None,
    *,
    now: datetime | None = None,
    tolerance_days: int = DEFAULT_TOLERANCE_DAYS,
) -> tuple[bool, str | None]:
    """Return ``(suspected, reason)`` for artificially re-dated content (§41.7).

    Args:
        stated_published_at: the publish date the source presents.
        content_date: the real date of the underlying content, when known.
        now: reference instant; defaults to the current UTC time.
        tolerance_days: allowed stated-vs-actual gap before suspicion.
    """
    if tolerance_days < 0:
        raise ValueError("tolerance_days must be >= 0")

    if stated_published_at is None:
        return False, None

    stated = _as_utc(stated_published_at)
    reference = _as_utc(now) if now is not None else datetime.now(timezone.utc)

    if stated > reference + _FUTURE_SLACK:
        return True, f"stated publish date {stated.date().isoformat()} is in the future"

    if content_date is not None:
        actual = _as_utc(content_date)
        if stated > actual:
            gap = (stated - actual).days
            if gap > tolerance_days:
                return True, (
                    f"stated date is {gap} days newer than the content date "
                    f"(tolerance {tolerance_days})"
                )

    return False, None
