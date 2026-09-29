"""§24.2/§41.14 — the artifact repository on the migrated schema.

Two properties only a real database can prove:

* ``ART_{YYYY}_{SEQ6}`` is allocated by the database, so it keeps increasing
  after the application restarts and never hands the same identifier twice — the
  in-memory fallback cannot promise either;
* writing the same §24.2 record twice is a no-op, not a primary-key violation
  (CODING_RULES §1.10: a replayed delivery must be safe).

Runs against the pgvector container (skipped when Docker is unavailable).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.artifacts.packager.artifact_sequence import format_artifact_id, parse_artifact_id
from app.storage.database.engine import create_engine
from app.storage.repositories.artifact_repository import ArtifactRepository
from tests.factories import make_artifact

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[Any]:
    """Yield an engine bound to the migrated PostgreSQL test database."""
    created = create_engine(db_url)
    try:
        yield created
    finally:
        await created.dispose()


def _record(**overrides: Any) -> dict[str, Any]:
    """Return a §24.2 record built from the artifact factory."""
    artifact = make_artifact(**overrides)
    record = artifact.to_dict()
    record["request_id"] = overrides.get("request_id")
    return record


class TestIdentifierAllocation:
    """§24.2 — ``ART_{YYYY}_{SEQ6}`` comes from the database, not from memory."""

    async def test_allocated_identifiers_increase(self, engine: Any) -> None:
        first = await ArtifactRepository.allocate_artifact_id(engine)
        second = await ArtifactRepository.allocate_artifact_id(engine)

        first_year, first_sequence = parse_artifact_id(first)
        second_year, second_sequence = parse_artifact_id(second)
        assert first_year == second_year
        assert second_sequence == first_sequence + 1

    async def test_sequence_survives_a_new_connection(self, engine: Any, db_url: str) -> None:
        """A restart must not restart the sequence (that would re-use an id)."""
        before = await ArtifactRepository.allocate_artifact_id(engine)

        other = create_engine(db_url)
        try:
            after = await ArtifactRepository.allocate_artifact_id(other)
        finally:
            await other.dispose()

        assert parse_artifact_id(after) == (
            parse_artifact_id(before)[0],
            parse_artifact_id(before)[1] + 1,
        )

    async def test_a_sequence_is_kept_per_year(self, engine: Any) -> None:
        """``ART_2026_…`` and ``ART_2027_…`` are two independent counters."""
        current = await ArtifactRepository.allocate_artifact_id(engine)
        other_year = await ArtifactRepository.allocate_artifact_id(engine, year=1999)

        assert parse_artifact_id(other_year)[0] == 1999
        assert parse_artifact_id(current)[0] != 1999


class TestPersistence:
    """§24.2 — the row is readable, listable by request, and replayable."""

    async def test_repository_is_exported_by_the_storage_package(self) -> None:
        """§32 — ``app.storage.repositories`` exposes the artifact repository."""
        from app.storage.repositories import ArtifactRepository as exported

        assert exported is ArtifactRepository

    async def test_create_then_get_returns_the_same_projection(self, engine: Any) -> None:
        record = _record(artifact_id=format_artifact_id(1998, 1), request_id="REQ_test")

        stored = await ArtifactRepository.create(engine, record)
        read_back = await ArtifactRepository.get(engine, record["artifact_id"])

        assert stored["artifact_id"] == record["artifact_id"]
        assert read_back is not None
        assert read_back["artifact_id"] == record["artifact_id"]
        assert read_back["sha256"] == record["sha256"]
        assert read_back["source_ids"] == record["source_ids"]
        assert read_back["dataset_ids"] == record["dataset_ids"]
        assert read_back["storage_ref"] == record["storage_ref"]
        assert read_back["request_id"] == "REQ_test"
        assert read_back["created_at"] is not None

    async def test_creating_the_same_record_twice_is_idempotent(self, engine: Any) -> None:
        """A replayed delivery returns the stored row instead of raising."""
        record = _record(artifact_id=format_artifact_id(1997, 1), request_id="REQ_replay")

        first = await ArtifactRepository.create(engine, record)
        second = await ArtifactRepository.create(engine, record)

        assert first["artifact_id"] == second["artifact_id"]
        assert len(await ArtifactRepository.list_for_request(engine, "REQ_replay")) == 1

    async def test_an_unknown_artifact_is_not_invented(self, engine: Any) -> None:
        assert await ArtifactRepository.get(engine, format_artifact_id(1996, 999999)) is None

    async def test_listing_is_scoped_to_the_request(self, engine: Any) -> None:
        await ArtifactRepository.create(
            engine, _record(artifact_id=format_artifact_id(1995, 1), request_id="REQ_a")
        )
        await ArtifactRepository.create(
            engine, _record(artifact_id=format_artifact_id(1995, 2), request_id="REQ_b")
        )

        records = await ArtifactRepository.list_for_request(engine, "REQ_a")

        assert [item["artifact_id"] for item in records] == [format_artifact_id(1995, 1)]
        assert records[0]["request_id"] == "REQ_a"
