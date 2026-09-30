"""Unit tests of ``RequestRepository`` (§7, §27, L6.4).

The API kept its requests in a module-level dict: a restart erased the history.
These tests pin the durable subset — identity, objective, requester,
constraints, lifecycle status and the §41.1 checkpoint — and the explicit fact
that the other §7 fields are *not* stored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.storage.database.engine import create_engine
from app.storage.repositories.request_repository import (
    DEFAULT_TTL_SECONDS,
    RequestRepository,
    as_json_value,
    requests_table,
    to_request_row,
)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[object]:
    """A disposable SQLite engine (the PostgreSQL schema is Alembic's)."""
    built = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'requests.db'}")
    try:
        yield built
    finally:
        await built.dispose()


def test_table_mirrors_revision_0007() -> None:
    """The repository declares exactly the columns revision 0007 created."""
    assert set(requests_table.columns.keys()) == {
        "request_id",
        "request_type",
        "objective",
        "requester",
        "constraints",
        "status",
        "ttl_seconds",
        "resumable",
        "last_committed_step",
        "last_committed_at",
        "created_at",
        "updated_at",
    }


def test_row_defaults() -> None:
    """A minimal payload still produces a valid row."""
    row = to_request_row({"request_id": "REQ_L6_X", "objective": "objectif"})
    assert row["request_type"] == "research"
    assert row["status"] == "received"
    assert row["ttl_seconds"] == DEFAULT_TTL_SECONDS
    assert row["resumable"] is False


def test_pydantic_models_are_serialised() -> None:
    """§32 hands over models, not dicts: JSONB needs the dump."""

    class _Model:
        def model_dump(self, mode: str = "python") -> dict[str, object]:
            assert mode == "json"
            return {"json_only": False}

    assert as_json_value(_Model()) == {"json_only": False}
    assert as_json_value({"already": "json"}) == {"already": "json"}
    assert as_json_value(None) is None


@pytest.mark.asyncio
async def test_create_then_get_round_trip(engine: object) -> None:
    """The durable subset survives the trip to the table and back."""
    await RequestRepository.create(
        engine,
        {
            "request_id": "REQ_L6_1",
            "request_type": "research",
            "objective": "Persister la demande",
            "requester": {"id": "agent:dev"},
            "constraints": {"region": "EU"},
            "created_at": "2026-09-30T10:00:00+00:00",
        },
    )
    stored = await RequestRepository.get(engine, "REQ_L6_1")
    assert stored is not None
    assert stored["objective"] == "Persister la demande"
    assert stored["requester"] == {"id": "agent:dev"}
    assert stored["constraints"] == {"region": "EU"}
    assert stored["created_at"].startswith("2026-09-30T10:00:00")


@pytest.mark.asyncio
async def test_absent_request_is_none(engine: object) -> None:
    """An unknown identifier is ``None``: the API answers 404, not a blank row."""
    assert await RequestRepository.get(engine, "REQ_L6_ABSENT") is None


@pytest.mark.asyncio
async def test_list_recent_returns_the_newest_first(engine: object) -> None:
    """The history is ordered by creation, newest first."""
    await RequestRepository.create(
        engine, {"request_id": "REQ_L6_OLD", "created_at": "2026-09-01T00:00:00+00:00"}
    )
    await RequestRepository.create(
        engine, {"request_id": "REQ_L6_NEW", "created_at": "2026-09-30T00:00:00+00:00"}
    )
    recent = await RequestRepository.list_recent(engine, limit=10)
    assert recent[0]["request_id"] == "REQ_L6_NEW"


@pytest.mark.asyncio
async def test_update_status_records_the_resume_checkpoint(engine: object) -> None:
    """§41.1: the last committed step is stored with its timestamp."""
    await RequestRepository.create(engine, {"request_id": "REQ_L6_2"})
    await RequestRepository.update_status(engine, "REQ_L6_2", "executing", step="search")
    stored = await RequestRepository.get(engine, "REQ_L6_2")
    assert stored is not None
    assert stored["status"] == "executing"
    assert stored["last_committed_step"] == "search"
    assert stored["last_committed_at"] is not None
