"""§41.5 L2 cache backend on the ``cache_entries`` table (async).

The cache store's synchronous API cannot await PostgreSQL: this backend is the
**asynchronous** half, injected into :class:`~app.storage.cache.cache_store.CacheStore`
and used by the code paths that are already async (the pipeline's web stage).

A missing database is not an error: :meth:`available` is ``False``, the store
falls back to L1 only, and the caller states the limitation — a cache that
silently pretends to persist would be worse than no cache.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.time import utc_now
from app.storage.cache.cache_store import L2, CacheEntry
from app.storage.database.engine import get_default_engine
from app.storage.repositories.cache_repository import CacheEntryRepository

__all__ = ["PostgresCacheBackend"]


class PostgresCacheBackend:
    """The §41.5 L2 cache entries, read and written in PostgreSQL."""

    def __init__(self, engine: Any | None = None) -> None:
        """Bind the backend to *engine*, or to ``INIS_DATABASE_URL`` lazily."""
        self._engine = engine

    def _resolve(self) -> Any | None:
        """Return the engine to use, or ``None`` when no database is configured."""
        return self._engine if self._engine is not None else get_default_engine()

    @property
    def available(self) -> bool:
        """Return whether a database is usable for the L2 level."""
        return self._resolve() is not None

    async def aget(self, cache_key: str) -> CacheEntry | None:
        """Return the stored entry of *cache_key*, or ``None``."""
        engine = self._resolve()
        if engine is None:
            return None
        row = await CacheEntryRepository.get(engine, cache_key)
        if row is None:
            return None
        return CacheEntry(
            key=str(row["cache_key"]),
            value=row.get("payload"),
            level=str(row.get("level") or L2),
            source_freshness=row.get("source_freshness"),
            created_at=row.get("created_at") or utc_now(),
            expires_at=row.get("expires_at"),
            source_id=row.get("source_id"),
        )

    async def aset(self, entry: CacheEntry, ttl_seconds: int) -> bool:
        """Persist *entry*; the TTL is already carried by ``entry.expires_at``."""
        engine = self._resolve()
        if engine is None:
            return False
        expires_at = entry.expires_at
        if expires_at is None and ttl_seconds > 0:
            expires_at = utc_now() + timedelta(seconds=ttl_seconds)
        await CacheEntryRepository.put(
            engine,
            {
                "cache_key": entry.key,
                "namespace": entry.key.split(":", 1)[0],
                # The row *is* the L2 copy: whatever level the in-process entry
                # carries, this table only ever stores the durable level.
                "level": L2,
                "payload": entry.value,
                "source_id": entry.source_id,
                "source_freshness": entry.source_freshness,
                "expires_at": expires_at,
                "created_at": entry.created_at,
            },
        )
        return True

    async def adelete(self, cache_key: str) -> bool:
        """Remove one entry from L2."""
        engine = self._resolve()
        if engine is None:
            return False
        return await CacheEntryRepository.drop(engine, cache_key)

    async def ainvalidate_source(self, source_id: str) -> int:
        """Drop every L2 entry of one source (§41.5 ``on_source_update``)."""
        engine = self._resolve()
        if engine is None:
            return 0
        return await CacheEntryRepository.drop_source(engine, source_id)

    async def ainvalidate_namespace(self, namespace: str) -> int:
        """Drop every L2 entry of one namespace."""
        engine = self._resolve()
        if engine is None:
            return 0
        return await CacheEntryRepository.drop_namespace(engine, namespace)

    async def apurge_expired(self, now: datetime | None = None) -> int:
        """Drop the L2 entries whose TTL elapsed."""
        engine = self._resolve()
        if engine is None:
            return 0
        return await CacheEntryRepository.drop_expired(engine, now)

    async def acount(self, namespace: str | None = None) -> int:
        """Return how many entries L2 holds (diagnostics and tests)."""
        engine = self._resolve()
        if engine is None:
            return 0
        return await CacheEntryRepository.count(engine, namespace)
