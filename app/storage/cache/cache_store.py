"""Two-level operational cache with freshness-aware invalidation (§41.5).

The spec distinguishes three levels:

* **L1 — Redis** : recent Web search results and API responses, short TTL.
* **L2 — PostgreSQL** : already extracted and validated information units.
* **L3 — pgvector** : persistent embeddings (not handled here).

and the invalidation policy::

    {"on_source_update": true, "on_conflict_detected": true,
     "on_quality_failure": true, "max_ttl_seconds": 3600,
     "freshness_threshold_hours": 24}

The hard rule of §41.5 is implemented by :meth:`CacheStore.get`: **an entry
must not be reused when its ``source_freshness`` is below the freshness
threshold of the current request.**

Backends are duck-typed behind the :class:`CacheBackend` protocol so the store
works with the in-memory backend used by default and with a real Redis client
when ``REDIS_URL`` is configured, without adding a hard dependency.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from app.core.time import utc_now as _utc_now

#: The two cache levels handled here (L3 = pgvector lives elsewhere).
L1 = "L1"
L2 = "L2"

#: §41.5 — the third level. It is **not** a copy of an L1/L2 entry: L3 stores
#: embeddings, whose identity is a digest of the embedded text, whose model and
#: width decide whether a hit is legal, and which are invalidated by a new
#: version. It therefore has its own dedicated surface on :class:`CacheStore`
#: (:meth:`CacheStore.aget_l3` / :meth:`CacheStore.aset_l3`) instead of reusing
#: the single-key ``aget`` — a lookup that cannot be given the text digest, the
#: model or the width could only produce false hits.
L3 = "L3"

#: The invalidation triggers of §41.5.
INVALIDATION_TRIGGERS: tuple[str, ...] = (
    "on_source_update",
    "on_conflict_detected",
    "on_quality_failure",
)


def _iso_z(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def make_cache_key(namespace: str, *parts: Any) -> str:
    """Return a deterministic cache key for *namespace* and *parts*."""
    payload = json.dumps([str(part) for part in parts], sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{namespace}:{digest}"


@dataclass(frozen=True)
class CacheInvalidationPolicy:
    """The §41.5 ``[CONFIG]`` invalidation policy."""

    on_source_update: bool = True
    on_conflict_detected: bool = True
    on_quality_failure: bool = True
    max_ttl_seconds: int = 3600
    freshness_threshold_hours: int = 24

    def __post_init__(self) -> None:
        if self.max_ttl_seconds < 1:
            raise ValueError("max_ttl_seconds must be >= 1")
        if self.freshness_threshold_hours < 0:
            raise ValueError("freshness_threshold_hours must be >= 0")

    def should_invalidate(self, trigger: str) -> bool:
        """Return whether *trigger* invalidates the cache.

        Raises:
            KeyError: if *trigger* is not a §41.5 invalidation trigger.
        """
        if trigger not in INVALIDATION_TRIGGERS:
            raise KeyError(
                f"unknown trigger '{trigger}' (expected one of {INVALIDATION_TRIGGERS})"
            )
        return bool(getattr(self, trigger))

    def freshness_cutoff(self, now: datetime | None = None) -> datetime:
        """Return the oldest acceptable ``source_freshness`` instant."""
        return (now or _utc_now()) - timedelta(hours=self.freshness_threshold_hours)

    def clamp_ttl(self, ttl_seconds: int | None) -> int:
        """Return the effective TTL, capped by ``max_ttl_seconds``."""
        if ttl_seconds is None:
            return self.max_ttl_seconds
        return max(0, min(int(ttl_seconds), self.max_ttl_seconds))

    def to_dict(self) -> dict[str, Any]:
        """Return the §41.5 ``[CONFIG]`` block."""
        return {
            "on_source_update": self.on_source_update,
            "on_conflict_detected": self.on_conflict_detected,
            "on_quality_failure": self.on_quality_failure,
            "max_ttl_seconds": self.max_ttl_seconds,
            "freshness_threshold_hours": self.freshness_threshold_hours,
        }


@dataclass
class CacheEntry:
    """One cached value plus the freshness metadata §41.5 requires."""

    key: str
    value: Any
    level: str = L1
    source_freshness: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    expires_at: datetime | None = None
    source_id: str | None = None
    #: Contexte de l'entrée, pour un niveau qui en porte un (L3 : modèle,
    #: dimensions, empreinte du texte). Vide pour L1/L2, dont l'invalidation
    #: ne repose que sur la fraîcheur et le TTL.
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether the entry TTL elapsed."""
        if self.expires_at is None:
            return False
        return (now or _utc_now()) >= self.expires_at

    def is_fresh_enough(self, policy: CacheInvalidationPolicy, now: datetime | None = None) -> bool:
        """Return whether ``source_freshness`` clears the policy threshold.

        §41.5: a cached entry MUST NOT be reused when its source freshness is
        below the threshold of the current request. An entry without freshness
        metadata is treated as reusable only when the threshold is zero.
        """
        if policy.freshness_threshold_hours <= 0:
            return True
        if self.source_freshness is None:
            return False
        return self.source_freshness >= policy.freshness_cutoff(now)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection of this entry."""
        return {
            "key": self.key,
            "level": self.level,
            "value": self.value,
            "source_id": self.source_id,
            "source_freshness": _iso_z(self.source_freshness) if self.source_freshness else None,
            "created_at": _iso_z(self.created_at),
            "expires_at": _iso_z(self.expires_at) if self.expires_at else None,
            "metadata": dict(self.metadata),
        }


class CacheBackend(Protocol):
    """Minimal cache surface (in-memory dict, Redis client, …)."""

    def get(self, key: str) -> Any | None:
        """Return the raw value stored under *key*, or None."""
        ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store *value* under *key* for *ttl_seconds*."""
        ...

    def delete(self, key: str) -> bool:
        """Remove *key*; return whether something was removed."""
        ...


class InMemoryBackend:
    """Default backend: a TTL-aware in-process dictionary."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[Any, float | None]] = {}
        self._clock = time.monotonic

    def get(self, key: str) -> Any | None:
        """Return the value of *key*, or None when absent or expired."""
        item = self._values.get(key)
        if item is None:
            return None
        value, expiry = item
        if expiry is not None and self._clock() >= expiry:
            del self._values[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store *value* under *key* for *ttl_seconds*."""
        expiry = self._clock() + ttl_seconds if ttl_seconds > 0 else None
        self._values[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        """Remove *key* from the backend."""
        return self._values.pop(key, None) is not None

    def clear(self) -> None:
        """Drop every entry (tests and administrative reset)."""
        self._values.clear()


class CacheStore:
    """L1/L2 cache enforcing the §41.5 freshness and invalidation rules.

    Usage::

        store = CacheStore()
        store.set("web_search", query, ["result"], source_freshness=...)
        store.get("web_search", query)   # None when the source went stale
    """

    def __init__(
        self,
        policy: CacheInvalidationPolicy | None = None,
        l1_backend: CacheBackend | None = None,
        l2_backend: CacheBackend | None = None,
        l2_async_backend: Any | None = None,
        l3_async_backend: Any | None = None,
    ) -> None:
        self.policy = policy or CacheInvalidationPolicy()
        # L1 defaults to the shared in-memory backend; L2 falls back to L1 so a
        # single-process deployment still behaves coherently.
        self._l1 = l1_backend or InMemoryBackend()
        self._l2 = l2_backend or self._l1
        #: §41.5 L2 in PostgreSQL: an *asynchronous* backend (the storage layer is
        #: async, the L1 API is sync). ``None`` keeps the store L1-only, and
        #: :meth:`l2_enabled` says which mode the process is in.
        self._l2_async = l2_async_backend
        #: §41.5 L3 — the pgvector level (embeddings). ``None`` when no database
        #: is configured: the caller then computes, and says so.
        self._l3_async = l3_async_backend
        self._index: dict[str, set[str]] = {}
        self.hits = 0
        self.misses = 0
        self.stale_rejections = 0
        self.l2_promotions = 0
        self.l2_writes = 0
        self.l3_hits = 0
        self.l3_writes = 0

    def l2_enabled(self) -> bool:
        """Return whether a durable L2 level is usable in this process."""
        backend = self._l2_async
        if backend is None:
            return False
        available = getattr(backend, "available", None)
        return available if isinstance(available, bool) else True

    def l3_enabled(self) -> bool:
        """Return whether the durable L3 (pgvector) level is usable here."""
        backend = self._l3_async
        if backend is None:
            return False
        available = getattr(backend, "available", None)
        return available if isinstance(available, bool) else True

    # -- §41.5 L3 (embeddings in pgvector) -------------------------------

    async def aget_l3(
        self,
        namespace: str,
        parts: tuple[Any, ...],
        *,
        owner_id: str,
        text_hash: str,
        model: str,
        dimension: int,
    ) -> Any | None:
        """Return the embedding of ``(owner, text, model, width)``, or ``None``.

        The keyword arguments are what make an L3 hit *legal*, and the backend is
        required to act on all of them:

        * ``owner_id`` — the unit (or document) the vector belongs to. The
          ``embeddings`` table is read per owner by §16.2, so a hit may never
          cross owners;
        * ``text_hash`` — the digest of the text to embed. The backend refuses a
          row whose ``metadata.text_hash`` differs, so two different texts can
          never share a vector;
        * ``model`` — a vector produced by another model is a vector of another
          space; reusing it would be a silent lie about the answer's meaning;
        * ``dimension`` — a row of another width cannot be compared, inserted or
          searched against the expected one.

        Returns:
            The stored value (the vector) when it exists and matches, else
            ``None``. Nothing is ever invented: absence is an absence.
        """
        if self._l3_async is None:
            return None
        key = make_cache_key(namespace, *parts)
        entry: CacheEntry | None = await self._l3_async.aget(
            key,
            owner_id=owner_id,
            text_hash=text_hash,
            model=model,
            dimension=dimension,
        )
        if entry is None:
            self.misses += 1
            self._record_cache(False)
            return None
        self.l3_hits += 1
        self._record_cache(True)
        # L3 is durable by design; L1 is not populated from it, because an
        # embedding is already one cheap read and a second store to invalidate.
        return entry.value

    async def aset_l3(
        self,
        namespace: str,
        parts: tuple[Any, ...],
        *,
        value: Any,
        text_hash: str,
        model: str,
        dimension: int,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Persist an embedding in L3; return whether it was written.

        The entry carries what explains a future hit: the digest of the embedded
        text, the model, the width, and the caller's metadata (source, stage…).
        An L3 entry has **no TTL**: §41.5 invalidates embeddings « par nouvelle
        version », not by time, so an expiry would be a rule the contract does
        not ask for.
        """
        if self._l3_async is None:
            return False
        key = make_cache_key(namespace, *parts)
        entry = CacheEntry(
            key=key,
            value=value,
            level=L3,
            source_id=source_id,
            source_freshness=_utc_now(),
            metadata={
                "text_hash": text_hash,
                "model": model,
                "dimension": dimension,
                **dict(metadata or {}),
            },
        )
        written = bool(await self._l3_async.aset(entry))
        if written:
            self.l3_writes += 1
        return written

    # -- §41.5 L2 (asynchronous) ----------------------------------------

    async def aget(self, namespace: str, *parts: Any) -> Any | None:
        """Return the value of a key, reading L1 then the durable L2 level.

        A value served from L2 is **promoted** into L1, so the second read of the
        same key in the same process does not touch the database. The §41.5 rules
        are applied to the L2 entry exactly as to an L1 one: an expired or too
        stale entry is dropped (not merely ignored) and never reused.
        """
        key = make_cache_key(namespace, *parts)
        cached = self.get(namespace, *parts)
        if cached is not None:
            return cached
        if self._l2_async is None:
            return None
        entry: CacheEntry | None = await self._l2_async.aget(key)
        if entry is None:
            return None
        if entry.is_expired() or not entry.is_fresh_enough(self.policy):
            # Drop it from L2 so the next run re-fetches instead of paying for a
            # database read that can only be rejected again.
            await self._l2_async.adelete(key)
            if not entry.is_expired():
                self.stale_rejections += 1
                self._record_stale()
            return None
        self._l1.set(key, entry, 0)
        self._index.setdefault(L1, set()).add(key)
        self.l2_promotions += 1
        self.hits += 1
        self._record_cache(True)
        return entry.value

    async def aset(
        self,
        namespace: str,
        *parts: Any,
        value: Any = None,
        ttl_seconds: int | None = None,
        source_freshness: datetime | None = None,
        source_id: str | None = None,
    ) -> CacheEntry:
        """Write an entry to L1 **and** to the durable L2 level when available."""
        entry = self.set(
            namespace,
            *parts,
            value=value,
            ttl_seconds=ttl_seconds,
            source_freshness=source_freshness,
            source_id=source_id,
        )
        if self._l2_async is not None:
            ttl = self.policy.clamp_ttl(ttl_seconds)
            written = await self._l2_async.aset(entry, ttl)
            if written:
                self.l2_writes += 1
        return entry

    async def ainvalidate_source(self, source_id: str) -> int:
        """Invalidate one source in L1 and in L2 (``on_source_update``)."""
        dropped = self.invalidate_source(source_id)
        if self._l2_async is not None:
            dropped += await self._l2_async.ainvalidate_source(source_id)
        return dropped

    async def ainvalidate_namespace(self, namespace: str) -> int:
        """Invalidate one namespace in L1 and in L2."""
        prefix = f"{namespace}:"
        dropped = 0
        for level, keys in list(self._index.items()):
            backend = self._backend(level)
            for key in list(keys):
                if key.startswith(prefix):
                    backend.delete(key)
                    keys.discard(key)
                    dropped += 1
        if self._l2_async is not None:
            dropped += await self._l2_async.ainvalidate_namespace(namespace)
        return dropped

    async def apurge_expired(self, now: datetime | None = None) -> int:
        """Purge the expired entries of the durable level."""
        if self._l2_async is None:
            return 0
        return int(await self._l2_async.apurge_expired(now))

    def _backend(self, level: str) -> CacheBackend:
        """Return the backend of *level*.

        Raises:
            ValueError: for an unknown level.
        """
        if level == L1:
            return self._l1
        if level == L2:
            return self._l2
        raise ValueError(f"unknown cache level '{level}' (expected L1 or L2)")

    def set(
        self,
        namespace: str,
        *parts: Any,
        value: Any = None,
        level: str = L1,
        ttl_seconds: int | None = None,
        source_freshness: datetime | None = None,
        source_id: str | None = None,
    ) -> CacheEntry:
        """Store *value* under the derived key and return the entry."""
        key = make_cache_key(namespace, *parts)
        ttl = self.policy.clamp_ttl(ttl_seconds)
        entry = CacheEntry(
            key=key,
            value=value,
            level=level,
            source_freshness=source_freshness,
            expires_at=_utc_now() + timedelta(seconds=ttl) if ttl else None,
            source_id=source_id,
        )
        backend = self._backend(level)
        backend.set(key, entry, ttl)
        self._index.setdefault(level, set()).add(key)
        return entry

    def get(
        self,
        namespace: str,
        *parts: Any,
        level: str = L1,
    ) -> Any | None:
        """Return the cached value, or None when absent, expired or too stale.

        This is the §41.5 hard rule: a value whose ``source_freshness`` is below
        the policy threshold is *never* reused.
        """
        key = make_cache_key(namespace, *parts)
        backend = self._backend(level)
        raw = backend.get(key)
        if raw is None:
            self.misses += 1
            self._record_cache(False)
            return None
        if not isinstance(raw, CacheEntry):
            self.misses += 1
            self._record_cache(False)
            return None
        if raw.is_expired():
            backend.delete(key)
            self.misses += 1
            self._record_cache(False)
            return None
        if not raw.is_fresh_enough(self.policy):
            # Too stale to reuse: drop it so the next call re-fetches.
            backend.delete(key)
            self.stale_rejections += 1
            self.misses += 1
            self._record_cache(False)
            self._record_stale()
            return None
        self.hits += 1
        self._record_cache(True)
        return raw.value

    # -- §34 metric feeds ------------------------------------------------

    def _record_cache(self, hit: bool) -> None:
        """Feed the §34 ``cache_hit_rate`` / ``stale_data_rate`` gauges."""
        try:
            from app.observability.metrics import record_outcome

            record_outcome("cache_hit_rate", failure=not hit)
            if hit:
                # A served entry passed both the TTL and the freshness gate.
                record_outcome("stale_data_rate", failure=False)
        except Exception:  # noqa: BLE001 - observability never breaks storage
            pass

    def _record_stale(self) -> None:
        """Feed the §34 ``stale_data_rate`` gauge on a staleness rejection."""
        try:
            from app.observability.metrics import record_outcome

            record_outcome("stale_data_rate", failure=True)
        except Exception:  # noqa: BLE001 - observability never breaks storage
            pass


    def delete(self, namespace: str, *parts: Any, level: str = L1) -> bool:
        """Remove one entry, returning whether it existed."""
        key = make_cache_key(namespace, *parts)
        self._backend(level).delete(key)
        self._index.get(level, set()).discard(key)
        return True

    def invalidate(self, trigger: str, *, source_id: str | None = None) -> int:
        """Invalidate entries per the §41.5 policy; return how many were dropped.

        Args:
            trigger: one of ``on_source_update``, ``on_conflict_detected``,
                ``on_quality_failure``.
            source_id: when given, only entries of that source are dropped.

        Raises:
            KeyError: for an unknown trigger.
        """
        if not self.policy.should_invalidate(trigger):
            return 0
        dropped = 0
        for level, keys in list(self._index.items()):
            backend = self._backend(level)
            for key in list(keys):
                raw = backend.get(key)
                if not isinstance(raw, CacheEntry):
                    continue
                if source_id is not None and raw.source_id != source_id:
                    continue
                backend.delete(key)
                keys.discard(key)
                dropped += 1
        return dropped

    def invalidate_source(self, source_id: str) -> int:
        """Convenience wrapper for ``on_source_update`` on one source."""
        return self.invalidate("on_source_update", source_id=source_id)

    def stats(self) -> dict[str, Any]:
        """Return hit/miss counters (feeds the §34 ``cache_hit_rate``)."""
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "stale_rejections": self.stale_rejections,
            "hit_rate": (self.hits / total) if total else 0.0,
            # §41.5 — which mode the process really ran in, and how much the
            # durable level served or stored: a claim of "L2 enabled" must be
            # readable, not assumed.
            "l2_enabled": self.l2_enabled(),
            "l2_promotions": self.l2_promotions,
            "l2_writes": self.l2_writes,
            # §41.5 L3 — the pgvector level, counted apart from L1/L2 so a
            # « cache hit » claim can say *which* level served it.
            "l3_enabled": self.l3_enabled(),
            "l3_hits": self.l3_hits,
            "l3_writes": self.l3_writes,
        }

    def clear(self) -> None:
        """Drop every cached entry (tests and administrative reset)."""
        for level in (L1, L2):
            backend = self._backend(level)
            for key in list(self._index.get(level, set())):
                backend.delete(key)
        self._index.clear()
