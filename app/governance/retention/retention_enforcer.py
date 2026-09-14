"""Retention enforcement per resource type (§41.9, in-memory by default).

Durations come from the injected ``policies`` mapping (``[CONFIG]`` in
production); ``DEFAULT_POLICIES`` are development defaults in days.
Expired records are *selected* here — physical deletion stays with
the storage layer (logical delete per §0.2 invariant 5).
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

#: Development-default retention durations in days (§41.9 keys).
DEFAULT_POLICIES: dict[str, int] = {
    "audit_events": 2555,  # 7 years (legal obligation, FR)
    "information_units": 365,
    "pii_data": 90,
    "embeddings": 365,
    "artifacts": 730,
}

Record = dict[str, Any]


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"created_at must be datetime or ISO string, got: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class RetentionEnforcer:
    """Select records past their per-type retention duration."""

    def __init__(self, policies: dict[str, int] | None = None) -> None:
        merged = dict(DEFAULT_POLICIES)
        if policies:
            for resource_type, days in policies.items():
                if days < 0:
                    raise ValueError(f"retention days must be >= 0 for {resource_type}")
                merged[resource_type] = days
        self._policies = merged

    @property
    def policies(self) -> dict[str, int]:
        """Return the active retention durations in days."""
        return dict(self._policies)

    def _days_for(self, resource_type: str) -> int:
        try:
            return self._policies[resource_type]
        except KeyError:
            raise ValueError(
                f"Unknown resource_type: {resource_type}. "
                f"Configured: {sorted(self._policies)}"
            ) from None

    def expiry_date(self, resource_type: str, created_at: datetime | str) -> datetime:
        """Return ``created_at + retention`` for a resource type."""
        from datetime import timedelta

        return _as_datetime(created_at) + timedelta(days=self._days_for(resource_type))

    def is_expired(
        self,
        resource_type: str,
        created_at: datetime | str,
        now: datetime | None = None,
    ) -> bool:
        """Return True when a record is past its retention duration."""
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment >= self.expiry_date(resource_type, created_at)

    def select_expired(
        self,
        resource_type: str,
        records: list[Record],
        now: datetime | None = None,
    ) -> list[Record]:
        """Return the records past their retention duration (no deletion)."""
        return [
            record
            for record in records
            if self.is_expired(resource_type, record["created_at"], now=now)
        ]
