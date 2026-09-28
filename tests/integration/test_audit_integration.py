"""Integration tests for the §20 audit trail on real PostgreSQL.

``AuditWriter`` is the only writer of ``audit_events``; §20 requires that a
delivery, a modification and a denial all leave a durable, hashed row. These
tests assert the write, the read-back and the integrity fields.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID
from app.governance.audit.audit_writer import AuditWriter
from app.storage.database.engine import create_engine

REQUIRED_FIELDS = {
    "actor_type",
    "actor_id",
    "action",
    "resource_type",
    "resource_id",
    "request_id",
    "result",
    "reason",
}


def _event(**overrides: str) -> dict:
    """Build a §20.1-compliant audit event."""
    event = {
        "actor_type": "agent",
        "actor_id": "AGT_AUDIT_TEST",
        "action": "delivery",
        "resource_type": "request",
        "resource_id": ULID.new("REQ_"),
        "request_id": ULID.new("REQ_"),
        "result": "success",
        "reason": "integration test",
    }
    event.update(overrides)
    return event


class TestAuditWrite:
    """§20.1 — every event is persisted with its technical metadata."""

    async def test_event_lands_in_the_table(self, db_url: str) -> None:
        """A written event is readable from ``audit_events``."""
        engine = create_engine(db_url)
        try:
            event = _event()
            stored = await AuditWriter(engine).write(event)
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT id, actor_type, actor_id, action, resource_id, "
                            "request_id, result, reason FROM audit_events WHERE id = :id"
                        ),
                        {"id": stored["audit_event_id"]},
                    )
                ).mappings().first()
        finally:
            await engine.dispose()

        assert row is not None
        assert row["actor_type"] == event["actor_type"]
        assert row["actor_id"] == event["actor_id"]
        assert row["action"] == event["action"]
        assert row["resource_id"] == event["resource_id"]
        assert row["result"] == event["result"]

    async def test_identifier_and_timestamp_are_generated(self, db_url: str) -> None:
        """The writer mints an ``AUD_`` identifier and a UTC timestamp."""
        engine = create_engine(db_url)
        try:
            stored = await AuditWriter(engine).write(_event())
        finally:
            await engine.dispose()
        assert stored["audit_event_id"].startswith("AUD_")
        assert ULID.is_valid(stored["audit_event_id"])
        assert str(stored["timestamp"]).endswith("Z")

    async def test_multiple_events_are_kept(self, db_url: str) -> None:
        """The table is append-only: N writes leave N rows."""
        engine = create_engine(db_url)
        writer = AuditWriter(engine)
        actor = "AGT_" + ULID.new("REQ_").removeprefix("REQ_")[-12:]
        try:
            for _ in range(3):
                await writer.write(_event(actor_id=actor))
            events = await AuditWriter.list_events_from_db(engine, actor_id=actor)
        finally:
            await engine.dispose()
        assert len(events) == 3
        assert {event["actor_id"] for event in events} == {actor}

    async def test_hashes_are_recorded(self, db_url: str) -> None:
        """``before``/``after`` snapshots are hashed for tamper evidence."""
        engine = create_engine(db_url)
        try:
            stored = await AuditWriter(engine).write(
                _event(action="update"),
                before={"status": "active"},
                after={"status": "archived"},
            )
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT before_hash, after_hash FROM audit_events "
                            "WHERE id = :id"
                        ),
                        {"id": stored["audit_event_id"]},
                    )
                ).mappings().first()
        finally:
            await engine.dispose()
        assert row["before_hash"] and row["after_hash"]
        assert row["before_hash"] != row["after_hash"]


class TestAuditReadBack:
    """§20 — the trail is queryable per actor."""

    async def test_filter_by_actor(self, db_url: str) -> None:
        """``list_events_from_db`` filters on ``actor_id``."""
        engine = create_engine(db_url)
        actor = "AGT_" + ULID.new("REQ_").removeprefix("REQ_")[-12:]
        try:
            await AuditWriter(engine).write(_event(actor_id=actor))
            matching = await AuditWriter.list_events_from_db(engine, actor_id=actor)
            everything = await AuditWriter.list_events_from_db(engine)
        finally:
            await engine.dispose()
        assert matching
        assert all(event["actor_id"] == actor for event in matching)
        assert len(everything) >= len(matching)

    async def test_unknown_actor_returns_nothing(self, db_url: str) -> None:
        """An actor with no event yields an empty list."""
        engine = create_engine(db_url)
        try:
            events = await AuditWriter.list_events_from_db(
                engine, actor_id="AGT_NEVER_SEEN"
            )
        finally:
            await engine.dispose()
        assert events == []


class TestAuditContract:
    """§20.1 — the writer refuses incomplete events."""

    @pytest.mark.parametrize("missing", sorted(REQUIRED_FIELDS))
    async def test_missing_required_field_is_refused(
        self, db_url: str, missing: str
    ) -> None:
        """Every required §20.1 field is mandatory."""
        event = _event()
        event.pop(missing)
        engine = create_engine(db_url)
        try:
            with pytest.raises(ValidationError, match=missing):
                await AuditWriter(engine).write(event)
        finally:
            await engine.dispose()

    async def test_in_memory_writer_needs_no_database(self) -> None:
        """Without an engine the writer keeps the event in memory (§20 fallback)."""
        writer = AuditWriter()
        stored = await writer.write(_event(actor_id="AGT_MEMORY"))
        ids = {
            event["audit_event_id"]
            for event in await writer.list_events("AGT_MEMORY")
        }
        assert stored["audit_event_id"] in ids

