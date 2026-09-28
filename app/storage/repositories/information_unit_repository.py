"""Information Unit repository on the migrated schema (§11, §27, §32).

The table mirrors ``information_units`` (revision 0002) plus the §11 columns
added by revision 0011 (``raw_reference``, ``context``, ``language``,
``epistemic_status``, ``provenance``, ``updated_at``). ``search_vector`` is
intentionally absent from this definition: it is a PostgreSQL-only
``tsvector`` maintained by the revision 0012 trigger, never written by the
application (which would fight the trigger).

Before this repository existed, ``GET /v1/information/{id}`` only read a
process-local dict the pipeline never filled, so every persisted unit answered
404 while its row was sitting in PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
)

__all__ = ["InformationUnitRepository", "information_units_table"]

information_units_metadata = MetaData()

information_units_table = Table(
    "information_units",
    information_units_metadata,
    Column("id", String(64), primary_key=True),
    Column("type", String(32), nullable=False),
    Column("content", JSON_TYPE, nullable=False),
    Column("source_id", String(64), nullable=False),
    Column("document_id", String(64), nullable=True),
    Column("data_stage", String(32), nullable=False),
    Column("raw_reference", JSON_TYPE, nullable=True),
    Column("context", JSON_TYPE, nullable=True),
    Column("language", String(16), nullable=True),
    Column("epistemic_status", String(32), nullable=True),
    Column("provenance", JSON_TYPE, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)


def to_information_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``information_units`` row onto the §11 API payload."""
    data = dict(row)
    information_id = data.get("id")
    return {
        "information_id": information_id,
        "type": data.get("type") or "text",
        "content": as_dict(data.get("content")),
        "raw_reference": as_dict(data.get("raw_reference")),
        "source_id": data.get("source_id"),
        "document_id": data.get("document_id"),
        "dataset_id": None,
        "context": as_dict(data.get("context")),
        "language": data.get("language"),
        "provenance": as_dict(data.get("provenance")),
        "data_stage": data.get("data_stage") or "raw",
        "epistemic_status": data.get("epistemic_status") or "factual",
        # §18.1 — a stored unit is its own first version.
        "versions": [information_id] if information_id else [],
        "created_at": as_iso(data.get("created_at")),
        "updated_at": as_iso(data.get("updated_at")),
    }


class InformationUnitRepository(TableRepository):
    """Persistence of the §11 information units."""

    _metadata = information_units_metadata
    _table = information_units_table

    @classmethod
    async def get(cls, engine: Any, information_id: str) -> dict[str, Any] | None:
        """Return one information unit by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(information_units_table).where(
                    information_units_table.c.id == information_id
                )
            )
            row = result.mappings().first()
        return to_information_response(row) if row else None

    @classmethod
    async def list(
        cls,
        engine: Any,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List information units, newest first, optionally filtered by source."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            query = (
                select(information_units_table)
                .order_by(information_units_table.c.created_at.desc())
                .limit(limit)
            )
            if source_id:
                query = query.where(information_units_table.c.source_id == source_id)
            result = await conn.execute(query)
            return [to_information_response(row) for row in result.mappings().all()]

    @classmethod
    async def create(cls, engine: Any, unit: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one information unit and return its §11 representation."""
        await cls.ensure_table(engine)
        item = dict(unit)
        information_id = str(item.get("information_id") or ULID.new("INF_"))
        now = datetime.now(timezone.utc)
        row = {
            "id": information_id,
            "type": item.get("type") or "text",
            "content": dict(item.get("content") or {}),
            "source_id": item.get("source_id") or "SRC_UNKNOWN",
            # ``document_id`` carries a foreign key to ``documents``: a document
            # that is not registered yet must not be referenced.
            "document_id": None,
            "data_stage": item.get("data_stage") or "raw",
            "raw_reference": dict(item.get("raw_reference") or {}),
            "context": dict(item.get("context") or {}),
            "language": item.get("language"),
            "epistemic_status": item.get("epistemic_status") or "factual",
            "provenance": dict(item.get("provenance") or {}),
            "created_at": as_datetime(item.get("created_at"), now),
            "updated_at": as_datetime(item.get("updated_at"), now),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(information_units_table).values(**row))
        return to_information_response(row)


def get_database_engine() -> Any | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` (in-memory mode)."""
    return get_default_engine()
