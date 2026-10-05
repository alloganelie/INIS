"""Cache entry repository on the migrated ``cache_entries`` table (§41.5, §27).

Revision ``0008`` created the table; nothing ever wrote to it, so the §41.5 L2
cache ("already extracted and validated information units") was a schema without
an implementation: a cache entry disappeared with the process.

The repository is **async** because the storage layer is (asyncpg): the cache
store keeps its synchronous L1 API and gains an asynchronous L2 path, documented
in :mod:`app.storage.cache.cache_store`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Table, delete, func, select, update

from app.core.time import utc_now
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    insert_statement,
)

__all__ = ["CacheEntryRepository", "cache_entries_table"]

#: Internal row identifier prefix. **Not** a ULID prefix on purpose: §0.3's table
#: is closed and carries no cache entry (a cache entry is disposable operational
#: state, not a §0.3 business object). The identifier is derived from the cache
#: key, which is the natural identity of the row (``cache_key`` is UNIQUE).
CACHE_ID_PREFIX = "cache-"

cache_metadata = MetaData()

cache_entries_table = Table(
    "cache_entries",
    cache_metadata,
    Column("cache_entry_id", String(64), primary_key=True),
    Column("cache_key", String(128), nullable=False, unique=True),
    Column("namespace", String(100), nullable=False),
    Column("level", String(4), nullable=False),
    Column("payload", JSON_TYPE, nullable=True),
    Column("source_id", String(64), nullable=True),
    Column("source_freshness", DateTime(timezone=True), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def cache_entry_id(cache_key: str) -> str:
    """Return the deterministic row identifier of *cache_key*.

    Derived from the key so the same entry always has the same identifier, and
    so nothing pretends to be a §0.3 ULID that the closed prefix table does not
    define (see :data:`CACHE_ID_PREFIX`).
    """
    return CACHE_ID_PREFIX + hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:32]


def to_cache_row(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Map a §41.5 cache entry onto its ``cache_entries`` row."""
    item = dict(entry)
    key = str(item.get("cache_key") or "")
    return {
        "cache_entry_id": str(item.get("cache_entry_id") or cache_entry_id(key)),
        "cache_key": key,
        "namespace": str(item.get("namespace") or "web"),
        "level": str(item.get("level") or "L2"),
        "payload": item.get("payload"),
        "source_id": item.get("source_id"),
        "source_freshness": as_datetime(item.get("source_freshness")),
        "expires_at": as_datetime(item.get("expires_at")),
        "created_at": as_datetime(item.get("created_at"), utc_now()),
    }


def to_cache_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``cache_entries`` row onto the §41.5 entry payload."""
    data = dict(row)
    return {
        "cache_entry_id": data.get("cache_entry_id"),
        "cache_key": data.get("cache_key"),
        "namespace": data.get("namespace"),
        "level": data.get("level"),
        "payload": data.get("payload"),
        "source_id": data.get("source_id"),
        "source_freshness": as_datetime(data.get("source_freshness")),
        "expires_at": as_datetime(data.get("expires_at")),
        "created_at": as_datetime(data.get("created_at")),
    }


class CacheEntryRepository(TableRepository):
    """Persistence of the §41.5 L2 cache entries."""

    _metadata = cache_metadata
    _table = cache_entries_table

    @classmethod
    async def get(cls, engine: Any, cache_key: str) -> dict[str, Any] | None:
        """Return one entry by its cache key, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(cache_entries_table).where(cache_entries_table.c.cache_key == cache_key)
            )
            row = result.mappings().first()
        return to_cache_response(row) if row else None

    @classmethod
    async def put(cls, engine: Any, entry: Mapping[str, Any]) -> dict[str, Any]:
        """Insert or replace the entry of ``cache_key`` (one row per key)."""
        await cls.ensure_table(engine)
        row = to_cache_row(entry)
        statement = insert_statement(cache_entries_table, engine).values(**row)
        statement = statement.on_conflict_do_update(
            index_elements=["cache_key"],
            set_={
                "namespace": row["namespace"],
                "level": row["level"],
                "payload": row["payload"],
                "source_id": row["source_id"],
                "source_freshness": row["source_freshness"],
                "expires_at": row["expires_at"],
                "created_at": row["created_at"],
            },
        )
        async with engine.begin() as conn:
            await conn.execute(statement)
        return to_cache_response(row)

    @classmethod
    async def drop(cls, engine: Any, cache_key: str) -> bool:
        """Remove one entry, returning whether a row was deleted."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(cache_entries_table).where(cache_entries_table.c.cache_key == cache_key)
            )
        return bool(result.rowcount)

    @classmethod
    async def drop_source(cls, engine: Any, source_id: str) -> int:
        """Drop every entry of one source (§41.5 ``on_source_update``)."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(cache_entries_table).where(cache_entries_table.c.source_id == source_id)
            )
        return int(result.rowcount or 0)

    @classmethod
    async def drop_namespace(cls, engine: Any, namespace: str) -> int:
        """Drop every entry of one namespace (administrative invalidation)."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(cache_entries_table).where(cache_entries_table.c.namespace == namespace)
            )
        return int(result.rowcount or 0)

    @classmethod
    async def drop_expired(cls, engine: Any, now: datetime | None = None) -> int:
        """Drop the entries whose TTL elapsed; return how many were removed."""
        await cls.ensure_table(engine)
        moment = now or utc_now()
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(cache_entries_table).where(
                    cache_entries_table.c.expires_at.is_not(None),
                    cache_entries_table.c.expires_at <= moment,
                )
            )
        return int(result.rowcount or 0)

    @classmethod
    async def touch(cls, engine: Any, cache_key: str, expires_at: datetime) -> None:
        """Extend the TTL of one entry (no payload rewrite)."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                update(cache_entries_table)
                .where(cache_entries_table.c.cache_key == cache_key)
                .values(expires_at=expires_at)
            )

    @classmethod
    async def count(cls, engine: Any, namespace: str | None = None) -> int:
        """Return how many entries are stored (optionally in one namespace)."""
        await cls.ensure_table(engine)
        query = select(func.count()).select_from(cache_entries_table)
        if namespace:
            query = query.where(cache_entries_table.c.namespace == namespace)
        async with engine.connect() as conn:
            return int((await conn.execute(query)).scalar_one())
