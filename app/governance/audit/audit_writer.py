"""In-memory and database-backed writers for INIS audit events."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import ValidationError
from app.core.hashing import after_hash as compute_after_hash
from app.core.hashing import before_hash as compute_before_hash
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
    """Write audit events in memory or to the configured asynchronous database."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._events: dict[str, dict] = {}

    async def write(
        self,
        event: dict,
        *,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
    ) -> None:
        """Store an audit event after adding its required technical metadata.

        Args:
            event: Audit event following the §20.1 contract.
            before: Optional snapshot of the record **before** the
                modification. Its deterministic SHA-256 fills ``before_hash``
                when the caller did not supply one.
            after: Optional snapshot of the record **after** the modification.
                Its deterministic SHA-256 fills ``after_hash`` when the caller
                did not supply one.

        Raises:
            ValidationError: If a required §20.1 field is missing.
        """
        missing_fields = _REQUIRED_EVENT_FIELDS.difference(event)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValidationError(f"Audit event is missing required fields: {missing}")

        stored_event = dict(event)
        stored_event.setdefault("audit_event_id", ULID.new("AUD_"))
        stored_event.setdefault("timestamp", self._utc_timestamp())
        stored_event.setdefault("before_hash", compute_before_hash(before))
        stored_event.setdefault("after_hash", compute_after_hash(after))
        if self._engine is None:
            self._events[stored_event["audit_event_id"]] = stored_event
            return

        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, timestamp, actor_type, actor_id, action, resource_type,
                        resource_id, request_id, result, reason, before_hash, after_hash
                    ) VALUES (
                        :id, :timestamp, :actor_type, :actor_id, :action, :resource_type,
                        :resource_id, :request_id, :result, :reason, :before_hash, :after_hash
                    )
                    """
                ),
                {**stored_event, "id": stored_event["audit_event_id"]},
            )

    async def list_events(self, actor_id: str | None = None) -> list[dict]:
        """Return copies of audit events, optionally limited to one actor."""
        return [
            dict(event)
            for event in self._events.values()
            if actor_id is None or event["actor_id"] == actor_id
        ]

    @staticmethod
    async def list_events_from_db(
        engine: AsyncEngine, actor_id: str | None = None
    ) -> list[dict]:
        """Read persisted audit events, optionally filtering them by actor."""
        statement = text(
            """
            SELECT
                id AS audit_event_id, timestamp, actor_type, actor_id, action,
                resource_type, resource_id, request_id, result, reason,
                before_hash, after_hash
            FROM audit_events
            """
            + (" WHERE actor_id = :actor_id" if actor_id is not None else "")
            + " ORDER BY timestamp"
        )
        parameters = {"actor_id": actor_id} if actor_id is not None else {}
        async with engine.connect() as connection:
            result = await connection.execute(statement, parameters)
        return [dict(event) for event in result.mappings().all()]

    @staticmethod
    def _utc_timestamp() -> str:
        """Format timestamps according to the INIS UTC identifier convention."""
        return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
