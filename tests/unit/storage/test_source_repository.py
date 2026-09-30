"""Unit tests of ``SourceRepository`` (§9, §27, L6.1).

These tests are the *offline* half of the plan's proof
``test_source_repository_matches_migration``: they pin the exact column set the
repository declares, so a change of one side without the other fails here
instead of failing at the first ``INSERT`` on a migrated database — which is
exactly what the ``source_id`` drift cost before L6. The PostgreSQL half lives
in ``tests/integration/test_postgres_real.py`` and compares the same metadata
with the *live* schema.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select

from app.storage.database.engine import create_engine
from app.storage.repositories.source_repository import (
    SourceRepository,
    sources_table,
    to_source_response,
)

#: ``migrations/versions/0002`` created the first eight, revision ``0011`` the
#: five §9 columns. The repository must declare exactly these.
EXPECTED_COLUMNS = {
    "id",
    "url",
    "source_type",
    "reliability_score",
    "freshness",
    "data_stage",
    "created_at",
    "updated_at",
    "name",
    "description",
    "trust_level",
    "status",
    "metadata",
}


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[object]:
    """A disposable SQLite engine (the PostgreSQL schema is Alembic's)."""
    built = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'sources.db'}")
    try:
        yield built
    finally:
        await built.dispose()


def test_repository_columns_match_the_migrations() -> None:
    """The repository declares the migrated columns, and only them."""
    assert set(sources_table.columns.keys()) == EXPECTED_COLUMNS


def test_primary_key_is_id_not_source_id() -> None:
    """``sources`` is keyed by ``id``: writing ``source_id`` cannot work."""
    assert sources_table.c.id.primary_key is True
    assert "source_id" not in sources_table.columns


@pytest.mark.asyncio
async def test_create_then_get_round_trip(engine: object) -> None:
    """A created source is readable, with its trust level on both columns."""
    created = await SourceRepository.create(
        engine,
        {
            "source_id": "SRC_L6_TESTS_1",
            "url": "https://example.org/report",
            "source_type": "web",
            "trust_level": 0.7,
            "name": "Rapport",
        },
    )
    assert created["source_id"] == "SRC_L6_TESTS_1"
    assert created["trust_level"] == 0.7

    stored = await SourceRepository.get(engine, "SRC_L6_TESTS_1")
    assert stored is not None
    assert stored["trust_level"] == 0.7
    assert stored["url"] == "https://example.org/report"


@pytest.mark.asyncio
async def test_internal_source_gets_a_scheme_url(engine: object) -> None:
    """``url`` is NOT NULL: an internal source stores a scheme, never ''."""
    created = await SourceRepository.create(
        engine, {"source_id": "SRC_L6_TESTS_2", "source_type": "internal"}
    )
    assert created["url"] == "internal://SRC_L6_TESTS_2"

    # ``data_stage`` is a §12 stage, not a §32 response field: read the row.
    async with engine.connect() as conn:  # type: ignore[attr-defined]
        row = (await conn.execute(select(sources_table))).mappings().first()
    assert row is not None
    assert row["data_stage"] == "raw"


@pytest.mark.asyncio
async def test_get_returns_none_when_absent(engine: object) -> None:
    """An unknown source is ``None``, never an invented row."""
    assert await SourceRepository.get(engine, "SRC_L6_ABSENT") is None


def test_response_falls_back_to_the_url_for_the_name() -> None:
    """A pipeline-written source has no human name: the URL is the label."""
    response = to_source_response(
        {"id": "SRC_1", "url": "https://example.org", "source_type": "web"}
    )
    assert response["name"] == "https://example.org"
    assert response["status"] == "active"
    assert response["trust_level"] == 1.0
