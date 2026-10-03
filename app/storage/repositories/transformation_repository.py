"""Transformation repository on the migrated ``transformations`` table (§12.1, §27).

Revision ``0004`` created the table; the §12.1 lineage projection (L3.2) finally
writes one row per executed transformation. Before this repository the write was
raw SQL typed inside ``app/api/v1/requests/pipeline_persistence.py`` — a second
definition of the same table, which is exactly the drift this lot removes:
``sources.id`` used to be written as ``source_id`` from that string and every
insert failed on the migrated schema.

The repository exposes two entry points for two owners:

* :meth:`TransformationRepository.create_many` — a repository owns its
  transaction (an engine);
* :meth:`TransformationRepository.insert_many_in` — the pipeline is already
  inside a unit of work (a live session) and must not open a second one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, Table, Text, select

from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    insert_rows,
)

__all__ = ["TransformationRepository", "transformations_table"]

transformations_metadata = MetaData()

transformations_table = Table(
    "transformations",
    transformations_metadata,
    Column("transformation_id", Text, primary_key=True),
    Column("input_ids", JSON_TYPE, nullable=False),
    Column("output_ids", JSON_TYPE, nullable=False),
    Column("operator", Text, nullable=True),
    Column("tool", Text, nullable=True),
    Column("tool_version", Text, nullable=True),
    Column("parameters", JSON_TYPE, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("result", Text, nullable=True),
    Column("justification", Text, nullable=True),
)


def to_transformation_row(transformation: Mapping[str, Any]) -> dict[str, Any]:
    """Map one §12.1 transformation onto its ``transformations`` row."""
    item = dict(transformation)
    return {
        "transformation_id": item.get("transformation_id"),
        "input_ids": list(item.get("input_ids") or []),
        "output_ids": list(item.get("output_ids") or []),
        "operator": item.get("operator"),
        "tool": item.get("tool"),
        "tool_version": item.get("tool_version"),
        "parameters": dict(item.get("parameters") or {}),
        "timestamp": as_datetime(item.get("timestamp"), datetime.now(UTC)),
        "result": item.get("result") or "success",
        "justification": item.get("justification"),
    }


def to_transformation_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``transformations`` row onto the §12.1 payload."""
    data = dict(row)
    timestamp = data.get("timestamp")
    return {
        "transformation_id": data.get("transformation_id"),
        "input_ids": list(data.get("input_ids") or []),
        "output_ids": list(data.get("output_ids") or []),
        "operator": data.get("operator"),
        "tool": data.get("tool"),
        "tool_version": data.get("tool_version"),
        "parameters": as_dict(data.get("parameters")),
        "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
        "result": data.get("result"),
        "justification": data.get("justification"),
    }


class TransformationRepository(TableRepository):
    """Persistence of the §12.1 transformations."""

    _metadata = transformations_metadata
    _table = transformations_table

    @classmethod
    async def insert_many_in(
        cls, session: Any, transformations: Sequence[Mapping[str, Any]]
    ) -> int:
        """Insert *transformations* inside an existing unit of work."""
        rows = [to_transformation_row(item) for item in transformations if item]
        return await insert_rows(
            session,
            transformations_table,
            rows,
            conflict_columns=("transformation_id",),
        )

    @classmethod
    async def create_many(
        cls, engine: Any, transformations: Sequence[Mapping[str, Any]]
    ) -> int:
        """Insert *transformations* in their own transaction."""
        await cls.ensure_table(engine)
        return await cls.insert_many_in(engine, transformations)

    @classmethod
    async def get(cls, engine: Any, transformation_id: str) -> dict[str, Any] | None:
        """Return one transformation by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(transformations_table).where(
                    transformations_table.c.transformation_id == transformation_id
                )
            )
            row = result.mappings().first()
        return to_transformation_response(row) if row else None

    @classmethod
    async def list_for_outputs(
        cls, engine: Any, output_ids: Sequence[str]
    ) -> list[dict[str, Any]]:
        """Return every transformation that produced one of *output_ids*.

        This is the lineage query of §12.1 read backwards: given a delivered
        unit, which transformations built it. ``output_ids`` is a JSONB array,
        so the filter is applied in Python on the ordered rows rather than with
        a dialect-specific containment operator.
        """
        wanted = {str(output_id) for output_id in output_ids if output_id}
        if not wanted:
            return []
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(transformations_table).order_by(transformations_table.c.timestamp)
            )
            rows = result.mappings().all()
        return [
            response
            for response in (to_transformation_response(row) for row in rows)
            if wanted & set(response["output_ids"] or [])
        ]

    @classmethod
    async def count(cls, engine: Any) -> int:
        """Return how many transformations are stored."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(select(transformations_table.c.transformation_id))
            return len(result.mappings().all())
