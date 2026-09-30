"""Unit tests of ``TransformationRepository`` (§12.1, §27, L6.2).

The §12.1 lineage used to be written by raw SQL typed inside the persistence
module. These tests pin the row mapping and the read paths of the repository
that now owns the table, including the backwards lineage query ("which
transformation produced this delivered unit?").
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.storage.database.engine import create_engine
from app.storage.repositories.transformation_repository import (
    TransformationRepository,
    to_transformation_response,
    to_transformation_row,
    transformations_table,
)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[object]:
    """A disposable SQLite engine (the PostgreSQL schema is Alembic's)."""
    built = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'transformations.db'}")
    try:
        yield built
    finally:
        await built.dispose()


def test_table_mirrors_revision_0004() -> None:
    """The repository declares exactly the columns revision 0004 created."""
    assert set(transformations_table.columns.keys()) == {
        "transformation_id",
        "input_ids",
        "output_ids",
        "operator",
        "tool",
        "tool_version",
        "parameters",
        "timestamp",
        "result",
        "justification",
    }


def test_row_mapping_defaults() -> None:
    """A payload with only an id still produces an insertable row."""
    row = to_transformation_row({"transformation_id": "TRF_1"})
    assert row["input_ids"] == []
    assert row["output_ids"] == []
    assert row["parameters"] == {}
    assert row["result"] == "success"
    assert row["timestamp"] is not None


def test_response_mapping_reads_json_columns() -> None:
    """A JSON column stored as a string is read back as a mapping."""
    response = to_transformation_response(
        {
            "transformation_id": "TRF_2",
            "input_ids": ["INF_A"],
            "output_ids": ["INF_B"],
            "parameters": '{"k": 1}',
            "result": "success",
        }
    )
    assert response["parameters"] == {"k": 1}
    assert response["output_ids"] == ["INF_B"]


@pytest.mark.asyncio
async def test_create_many_then_get(engine: object) -> None:
    """Stored transformations are readable one by one and counted."""
    written = await TransformationRepository.create_many(
        engine,
        [
            {
                "transformation_id": "TRF_L6_1",
                "input_ids": ["SRC_L6_1"],
                "output_ids": ["INF_L6_1"],
                "operator": "extract",
                "tool": "extract_facts",
                "tool_version": "1.0.0",
                "parameters": {"language": "fr"},
            }
        ],
    )
    assert written == 1

    stored = await TransformationRepository.get(engine, "TRF_L6_1")
    assert stored is not None
    assert stored["tool"] == "extract_facts"
    assert stored["parameters"] == {"language": "fr"}
    assert await TransformationRepository.count(engine) == 1


@pytest.mark.asyncio
async def test_list_for_outputs_finds_the_producer(engine: object) -> None:
    """The lineage query read backwards answers §12.1 for a delivered unit."""
    await TransformationRepository.create_many(
        engine,
        [
            {"transformation_id": "TRF_L6_A", "output_ids": ["INF_L6_A"]},
            {"transformation_id": "TRF_L6_B", "output_ids": ["INF_L6_B"]},
        ],
    )
    found = await TransformationRepository.list_for_outputs(engine, ["INF_L6_B"])
    assert [item["transformation_id"] for item in found] == ["TRF_L6_B"]
    assert await TransformationRepository.list_for_outputs(engine, []) == []


@pytest.mark.asyncio
async def test_empty_batch_is_a_noop(engine: object) -> None:
    """Writing nothing never opens a pointless statement."""
    assert await TransformationRepository.create_many(engine, []) == 0
    assert await TransformationRepository.count(engine) == 0
