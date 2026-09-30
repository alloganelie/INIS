"""Unit tests of ``DatasetRepository`` (§27, L6.2).

The repository landed with L1.3; L6 asks for its proof in the same breath as the
two that were missing (``transformation``, ``plan``), because the §13 quality lot
(L5) reads datasets back through it. The table is revision ``0007`` plus the
``storage_ref`` / ``request_id`` columns of a later revision.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.storage.database.engine import create_engine
from app.storage.repositories.dataset_repository import DatasetRepository, datasets_table


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[object]:
    """A disposable SQLite engine (the PostgreSQL schema is Alembic's)."""
    built = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'datasets.db'}")
    try:
        yield built
    finally:
        await built.dispose()


def test_table_mirrors_the_migrations() -> None:
    """Revision 0007 plus the columns added by later revisions, nothing else."""
    assert set(datasets_table.columns.keys()) == {
        "dataset_id",
        "name",
        "source_id",
        "row_count",
        "schema",
        "created_at",
        "storage_ref",
        "request_id",
    }


@pytest.mark.asyncio
async def test_create_then_get(engine: object) -> None:
    """A created dataset keeps its identifier, name and row count."""
    created = await DatasetRepository.create(
        engine,
        {
            "dataset_id": "DS_L6_1",
            "name": "ventes.csv",
            "row_count": 42,
            "request_id": "REQ_L6_1",
            "storage_ref": "s3://inis-artifacts/ventes.csv",
        },
    )
    assert created["dataset_id"] == "DS_L6_1"

    stored = await DatasetRepository.get(engine, "DS_L6_1")
    assert stored is not None
    assert stored["name"] == "ventes.csv"
    assert stored["row_count"] == 42


@pytest.mark.asyncio
async def test_missing_identifier_is_a_named_refusal(engine: object) -> None:
    """A dataset without an identifier is refused, never stored under a guess.

    ``create`` is idempotent on ``dataset_id`` (re-ingesting the same document
    returns the stored row), so the identifier is the caller's contract.
    """
    with pytest.raises(ValueError, match="dataset_id"):
        await DatasetRepository.create(engine, {"name": "sans id"})


@pytest.mark.asyncio
async def test_list_for_request_is_filtered(engine: object) -> None:
    """Only the datasets of the asked request come back."""
    await DatasetRepository.create(
        engine, {"dataset_id": "DS_L6_A", "name": "a.csv", "request_id": "REQ_L6_A"}
    )
    await DatasetRepository.create(
        engine, {"dataset_id": "DS_L6_B", "name": "b.csv", "request_id": "REQ_L6_B"}
    )
    found = await DatasetRepository.list_for_request(engine, "REQ_L6_B")
    assert [dataset["dataset_id"] for dataset in found] == ["DS_L6_B"]


@pytest.mark.asyncio
async def test_absent_dataset_is_none(engine: object) -> None:
    """An unknown identifier is ``None``, never an invented dataset."""
    assert await DatasetRepository.get(engine, "DS_L6_ABSENT") is None
