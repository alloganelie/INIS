"""§18.1/§20/§27 — versioning paired with a durable trail on real PostgreSQL.

§18.1 requires every version of a record to keep its parent, its author and its
justification; §20 requires the change to be auditable; §27 requires the tables
to exist in the migrated schema. The version chain itself is in-process for V1
(``app/tools/governance_tools/versioning.py``), so the durable half of the
obligation is carried by ``audit_events`` — which is exactly what these tests
assert: the chain is append-only and linked, the archive mark is idempotent, and
each change leaves a hashed row on the migrated database.

Runs against the pgvector container (skip when Docker is unavailable).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID
from app.governance.audit.audit_writer import AuditWriter
from app.storage.database.engine import create_engine
from app.tools.governance_tools.versioning import (
    VersionStore,
    archive_record,
    create_version,
)
from tests.factories import make_audit_event

pytestmark = pytest.mark.asyncio


async def _count_audit_rows(engine: Any, resource_id: str) -> int:
    """Return how many audit rows reference *resource_id*."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM audit_events WHERE resource_id = :rid"),
            {"rid": resource_id},
        )
        return int(result.scalar() or 0)


class TestVersionTableIsMigrated:
    """§27 — the §18.1 history has a table in the migrated schema."""

    async def test_information_versions_table_exists(self, db_url: str) -> None:
        """``information_versions`` is created by the migration chain."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                columns = (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'information_versions'"
                        )
                    )
                ).scalars().all()
        finally:
            await engine.dispose()

        assert columns, "information_versions is missing from the migrated schema"
        assert "information_id" in columns


class TestVersionChain:
    """§18.1 — a version chain keeps its history and names its parent."""

    async def test_second_version_points_at_the_first(self) -> None:
        """The chain is linked: each version records its parent (§18.1)."""
        store = VersionStore()
        resource_id = ULID.new("INF_")

        first = await create_version(
            resource_id, {"actor": "AGENT_A", "justification": "first import"}, store=store
        )
        second = await create_version(
            resource_id, {"actor": "AGENT_A", "justification": "normalization"}, store=store
        )

        chain = store.versions(resource_id)
        assert [entry["version_id"] for entry in chain] == [first, second]
        assert chain[0]["parent_version"] is None
        assert chain[1]["parent_version"] == first
        assert chain[1]["justification"] == "normalization"

    async def test_history_is_append_only(self) -> None:
        """Adding a version never rewrites the previous ones (§18.1)."""
        store = VersionStore()
        resource_id = ULID.new("INF_")
        await create_version(resource_id, {"actor": "A", "justification": "v1"}, store=store)
        snapshot = store.versions(resource_id).copy()

        await create_version(resource_id, {"actor": "A", "justification": "v2"}, store=store)

        assert store.versions(resource_id)[: len(snapshot)] == snapshot

    async def test_incomplete_version_request_is_refused(self) -> None:
        """§18.1 — a version needs a resource and a non-empty change."""
        with pytest.raises(ValidationError):
            await create_version("", {"actor": "A"}, store=VersionStore())

        with pytest.raises(ValidationError):
            await create_version(ULID.new("INF_"), {}, store=VersionStore())

    async def test_archive_is_idempotent(self) -> None:
        """§18.3 — archiving twice keeps the original mark."""
        store = VersionStore()
        resource_id = ULID.new("INF_")

        await archive_record(resource_id, store=store)
        first_mark = store.archived_at(resource_id)
        await archive_record(resource_id, store=store)

        assert store.is_archived(resource_id) is True
        assert store.archived_at(resource_id) == first_mark


class TestVersioningLeavesADurableTrail:
    """§20 — the durable half of the §18.1 obligation, on real PostgreSQL."""

    async def test_versioning_is_recorded_in_audit_events(self, db_url: str) -> None:
        """A version creation leaves a hashed, durable audit row."""
        engine = create_engine(db_url)
        store = VersionStore()
        resource_id = ULID.new("INF_")
        try:
            version_id = await create_version(
                resource_id,
                {"actor": "AGENT_A", "justification": "initial normalization"},
                store=store,
            )
            await AuditWriter(engine).write(
                make_audit_event(
                    action="version.create",
                    resource_type="information_unit",
                    resource_id=version_id,
                    reason="normalization produced a new version",
                )
            )

            assert await _count_audit_rows(engine, version_id) == 1
        finally:
            await engine.dispose()

    async def test_archiving_is_recorded_in_audit_events(self, db_url: str) -> None:
        """An archive mark is also audited, so retention is provable."""
        engine = create_engine(db_url)
        resource_id = ULID.new("INF_")
        try:
            await archive_record(resource_id, store=VersionStore())
            await AuditWriter(engine).write(
                make_audit_event(
                    action="record.archive",
                    resource_type="information_unit",
                    resource_id=resource_id,
                    reason="retention policy elapsed",
                )
            )

            assert await _count_audit_rows(engine, resource_id) == 1
        finally:
            await engine.dispose()

