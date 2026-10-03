"""Source repository on the migrated ``sources`` schema (§9, §27, §32).

The table mirrors ``migrations/versions/0002_create_core_tables.py`` plus the
canonical §9 columns added by revision ``0011`` (``name``, ``description``,
``trust_level``, ``status``, ``metadata``). Before this module existed the API
repository declared its own diverging table (``source_id`` / ``name`` /
``trust_level`` / ``status`` / ``metadata``) and, because ``create_all`` is a
no-op on a table that already exists, every read raised ``UndefinedColumn`` and
returned HTTP 500 on the migrated schema. The single Core definition below is
used for both paths: Alembic on PostgreSQL, ``create_all`` on SQLite.

``trust_level`` (API, §9) and ``reliability_score`` (schema 0002, §10.2) are
the same signal: ``create`` writes both so a row is readable from either side.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, Text, insert, select

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine, set_default_engine
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
)

__all__ = [
    "SourceRepository",
    "get_database_engine",
    "set_database_engine",
    "sources_table",
]

#: §9 source identity: a registered source is a raw acquisition target.
DEFAULT_DATA_STAGE = "raw"

sources_metadata = MetaData()

sources_table = Table(
    "sources",
    sources_metadata,
    Column("id", String(64), primary_key=True),
    Column("url", Text, nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("reliability_score", Float, nullable=True),
    Column("freshness", JSON_TYPE, nullable=True),
    Column("data_stage", String(32), nullable=False),
    Column("name", String(255), nullable=True),
    Column("description", Text, nullable=True),
    Column("trust_level", Float, nullable=True),
    Column("status", String(64), nullable=True),
    Column("metadata", JSON_TYPE, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    # Revision 0016 — §18.2: set when the record is soft-deleted; a read
    # filters on ``deleted_at IS NULL`` (partial index of the same name).
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


def get_database_engine() -> Any | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` (in-memory mode)."""
    return get_default_engine()


def set_database_engine(engine: Any | None) -> None:
    """Override (or clear) the engine used by the source endpoints."""
    set_default_engine(engine)


def to_source_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``sources`` row onto the §32 ``SourceResponse`` payload."""
    data = dict(row)
    trust_level = data.get("trust_level")
    if trust_level is None:
        trust_level = data.get("reliability_score")
    url = data.get("url")
    return {
        "source_id": data.get("id"),
        # A pipeline-written source has no human name: the URL is the honest
        # label, never an invented one.
        "name": data.get("name") or url or data.get("id"),
        "source_type": data.get("source_type"),
        "url": url,
        "description": data.get("description"),
        "trust_level": float(trust_level) if trust_level is not None else 1.0,
        "status": data.get("status") or "active",
        "metadata": as_dict(data.get("metadata")),
        "created_at": as_iso(data.get("created_at")),
        "updated_at": as_iso(data.get("updated_at")),
    }


class SourceRepository(TableRepository):
    """Persistence of the §9 sources, on the migrated schema."""

    _metadata = sources_metadata
    _table = sources_table

    @classmethod
    async def list(cls, engine: Any, source_type: str | None = None) -> list[dict[str, Any]]:
        """List sources, optionally filtered by ``source_type``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            query = select(sources_table).order_by(sources_table.c.created_at.desc())
            if source_type:
                query = query.where(sources_table.c.source_type == source_type)
            result = await conn.execute(query)
            return [to_source_response(row) for row in result.mappings().all()]

    @classmethod
    async def get(cls, engine: Any, source_id: str) -> dict[str, Any] | None:
        """Return one source by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(sources_table).where(sources_table.c.id == source_id)
            )
            row = result.mappings().first()
        return to_source_response(row) if row else None

    @classmethod
    async def create(cls, engine: Any, source_data: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a source and return its §32 representation."""
        await cls.ensure_table(engine)
        item = dict(source_data)
        source_id = str(item.get("source_id") or ULID.new("SRC_"))
        now = datetime.now(timezone.utc)
        trust_level = item.get("trust_level")
        row = {
            "id": source_id,
            # The column is NOT NULL (§27) and an internal source has no URL:
            # the internal scheme is stored instead of an empty string.
            "url": item.get("url") or f"internal://{source_id}",
            "source_type": item.get("source_type"),
            "reliability_score": float(trust_level) if trust_level is not None else None,
            "freshness": item.get("freshness"),
            "data_stage": item.get("data_stage") or DEFAULT_DATA_STAGE,
            "name": item.get("name"),
            "description": item.get("description"),
            "trust_level": float(trust_level) if trust_level is not None else None,
            "status": item.get("status") or "active",
            "metadata": dict(item.get("metadata") or {}),
            "created_at": as_datetime(item.get("created_at"), now),
            "updated_at": as_datetime(item.get("updated_at"), now),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(sources_table).values(**row))
        return to_source_response(row)
