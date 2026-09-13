"""In-memory writer for INIS audit events."""

from datetime import UTC, datetime

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID


_REQUIRED_EVENT_FIELDS = frozenset(
    {
        "actor_type",
        "actor_id",
        "action",
        "resource_type",
        "resource_id",
        "request_id",
        "result",
        "reason",
    }
)


class AuditWriter:
    """Keep audit events in memory until a persistent writer is introduced."""

    def __init__(self) -> None:
        self._events: dict[str, dict] = {}

    async def write(self, event: dict) -> None:
        """Store an audit event after adding its required technical metadata."""
        missing_fields = _REQUIRED_EVENT_FIELDS.difference(event)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValidationError(f"Audit event is missing required fields: {missing}")

        stored_event = dict(event)
        stored_event.setdefault("audit_event_id", ULID.new("AUD_"))
        stored_event.setdefault("timestamp", self._utc_timestamp())
        self._events[stored_event["audit_event_id"]] = stored_event

    async def list_events(self, actor_id: str | None = None) -> list[dict]:
        """Return copies of audit events, optionally limited to one actor."""
        return [
            dict(event)
            for event in self._events.values()
            if actor_id is None or event["actor_id"] == actor_id
        ]

    @staticmethod
    def _utc_timestamp() -> str:
        """Format timestamps according to the INIS UTC identifier convention."""
        return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
