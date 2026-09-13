"""Source repository for optional database persistence per §9, §27, §32."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, Float, MetaData, String, Table, insert, select
from sqlalchemy.types import JSON

from app.domain.value_objects.ulid import ULID

# Define the sources table schema for SQLAlchemy Core operations.
metadata = MetaData()

sources_table = Table(
    "sources",
    metadata,
    Column("source_id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("url", String(1024), nullable=True),
    Column("description", String(2048), nullable=True),
    Column("trust_level", Float, default=1.0),
    Column("status", String(64), default="active"),
    Column("metadata", JSON, default=dict),
    Column("created_at", String(64), nullable=True),
    Column("updated_at", String(64), nullable=True),
)

_DATABASE_ENGINE: Any | None = None
_CACHED_URL: str | None = None


def get_database_engine() -> Any | None:
    """Return an async database engine if INIS_DATABASE_URL is set, else None."""
    global _DATABASE_ENGINE, _CACHED_URL
    db_url = os.getenv("INIS_DATABASE_URL")
    if not db_url:
        return None
    if _DATABASE_ENGINE is None or _CACHED_URL != db_url:
        from app.storage.database.engine import create_engine

        _DATABASE_ENGINE = create_engine(db_url)
        _CACHED_URL = db_url
    return _DATABASE_ENGINE


def set_database_engine(engine: Any | None) -> None:
    """Explicitly set or reset the database engine (primarily for testing)."""
    global _DATABASE_ENGINE, _CACHED_URL
    _DATABASE_ENGINE = engine
    _CACHED_URL = None


class SourceRepository:
    """Repository handling persistence of Source records."""

    @staticmethod
    async def _ensure_table(engine: Any) -> None:
        """Ensure the sources table exists in the database."""
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    @classmethod
    async def list(cls, engine: Any, source_type: str | None = None) -> list[dict[str, Any]]:
        """List all sources, optionally filtered by source_type."""
        await cls._ensure_table(engine)
        async with engine.connect() as conn:
            query = select(sources_table).order_by(sources_table.c.created_at.desc())
            if source_type:
                query = query.where(sources_table.c.source_type == source_type)
            result = await conn.execute(query)
            rows = result.mappings().all()
            items: list[dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                if isinstance(d.get("metadata"), str):
                    try:
                        d["metadata"] = json.loads(d["metadata"])
                    except Exception:
                        pass
                if d.get("metadata") is None:
                    d["metadata"] = {}
                items.append(d)
            return items

    @classmethod
    async def get(cls, engine: Any, source_id: str) -> dict[str, Any] | None:
        """Retrieve a source by its source_id, or None if not found."""
        await cls._ensure_table(engine)
        async with engine.connect() as conn:
            query = select(sources_table).where(sources_table.c.source_id == source_id)
            result = await conn.execute(query)
            row = result.mappings().first()
            if not row:
                return None
            d = dict(row)
            if isinstance(d.get("metadata"), str):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except Exception:
                    pass
            if d.get("metadata") is None:
                d["metadata"] = {}
            return d

    @classmethod
    async def create(cls, engine: Any, source_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new source record and return the saved data dict."""
        await cls._ensure_table(engine)
        item = dict(source_data)
        if not item.get("source_id"):
            item["source_id"] = ULID.new("SRC_")
        now = datetime.now(timezone.utc).isoformat()
        item.setdefault("created_at", now)
        item.setdefault("updated_at", now)
        item.setdefault("trust_level", 1.0)
        item.setdefault("status", "active")
        meta = item.get("metadata") or {}
        item["metadata"] = meta

        stmt = insert(sources_table).values(
            source_id=item["source_id"],
            name=item["name"],
            source_type=item["source_type"],
            url=item.get("url"),
            description=item.get("description"),
            trust_level=float(item.get("trust_level", 1.0)),
            status=item.get("status", "active"),
            metadata=meta,
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
        async with engine.begin() as conn:
            await conn.execute(stmt)
        return item
