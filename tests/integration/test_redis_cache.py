"""§19/§41.5 — Redis is the shared-state backend, and it must really hold it.

Two components depend on Redis being *shared* rather than process-local:

* §19 token-bucket rate limiting (``create_rate_limit_store``), where two API
  replicas must meter the same actor against one budget;
* the §41.5 cache, whose ``CacheStore`` is backend-agnostic behind a duck-typed
  protocol — running it on Redis is what makes L1 shareable across replicas.

The tests below use the live Redis container and, for the cache, a thin Redis
adapter implementing exactly the ``CacheBackend`` protocol, so the store runs
against real Redis without adding a hard dependency to the application.

Runs against the Redis container (skip when Docker is unavailable).
"""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.security.rate_limiting.rate_limit_store import create_rate_limit_store
from app.security.rate_limiting.rate_limiter import RateLimiter
from app.storage.cache.cache_store import L1, L2, CacheStore, make_cache_key

pytestmark = pytest.mark.asyncio


class RedisCacheBackend:
    """``CacheBackend`` (§41.5) implemented on a real Redis client."""

    def __init__(self, client: Any, prefix: str = "inis:test:cache") -> None:
        self._client = client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def get(self, key: str) -> Any | None:
        """Return the stored entry, or ``None`` when absent or expired."""
        raw = self._client.get(self._key(key))
        if raw is None:
            return None
        return pickle.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store the entry with the given TTL."""
        payload = pickle.dumps(value)
        if ttl_seconds > 0:
            self._client.set(self._key(key), payload, ex=ttl_seconds)
        else:
            self._client.set(self._key(key), payload)

    def delete(self, key: str) -> bool:
        """Remove the entry; return whether it existed."""
        return bool(self._client.delete(self._key(key)))

    def clear(self) -> None:
        """Drop every entry written by this backend."""
        keys = list(self._client.scan_iter(match=f"{self._prefix}:*"))
        if keys:
            self._client.delete(*keys)


@pytest.fixture
def redis_client(redis_url: str) -> Iterator[Any]:
    """Return a synchronous Redis client bound to the live container."""
    import redis as redis_lib

    client = redis_lib.Redis.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        client.flushdb()
        client.close()


class TestRedisIsReachable:
    """§19 — the shared-state backend answers and keeps what it is given."""

    async def test_redis_container_serves_commands(self, redis_url: str) -> None:
        """A live Redis answers PING and stores a value durably."""
        import redis as redis_lib

        client = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        try:
            assert client.ping() is True
            client.set("inis:test:probe", "ok", ex=30)
            assert client.get("inis:test:probe") == "ok"
        finally:
            client.close()


class TestSharedRateLimiting:
    """§19 — two replicas meter the same actor against one budget."""

    async def test_bucket_is_shared_across_limiter_instances(self, redis_url: str) -> None:
        """A second limiter sees the tokens the first one consumed."""
        replica_a = RateLimiter(create_rate_limit_store(redis_url))
        replica_b = RateLimiter(create_rate_limit_store(redis_url))
        actor = "actor:shared-budget"
        try:
            allowed, _ = await replica_a.is_allowed(actor, capacity=3, refill_rate=0.0001)
            assert allowed is True

            allowed, remaining = await replica_b.is_allowed(actor, capacity=3, refill_rate=0.0001)
            assert allowed is True
            assert remaining < 3, "the second replica did not see the first consumption"

            await replica_a.reset(actor)
            _, refreshed = await replica_b.is_allowed(actor, capacity=3, refill_rate=0.0001)
            assert refreshed > remaining
        finally:
            await replica_a.aclose()
            await replica_b.aclose()

    async def test_budget_is_exhausted_and_reported(self, redis_url: str) -> None:
        """The bucket refuses once the capacity is consumed (§19)."""
        limiter = RateLimiter(create_rate_limit_store(redis_url))
        actor = "actor:exhausted"
        try:
            for _ in range(3):
                allowed, _ = await limiter.is_allowed(actor, capacity=3, refill_rate=0.0001)
                assert allowed is True

            allowed, remaining = await limiter.is_allowed(actor, capacity=3, refill_rate=0.0001)
            assert allowed is False
            assert remaining < 1
        finally:
            await limiter.aclose()


class TestCacheStoreOnRedis:
    """§41.5 — the cache backend protocol works against real Redis."""

    async def test_entry_survives_across_store_instances(self, redis_client: Any) -> None:
        """Two stores sharing the Redis backend see the same L1 entry.

        This is what makes L1 *shared*: the second store has an empty in-process
        index and must still serve what the first one wrote.
        """
        backend_a = RedisCacheBackend(redis_client)
        backend_b = RedisCacheBackend(redis_client)
        writer = CacheStore(l1_backend=backend_a)
        reader = CacheStore(l1_backend=backend_b)
        try:
            writer.set(
                "web_search",
                "capitale de la France",
                value=["Paris"],
                source_freshness=datetime.now(UTC),
            )

            assert reader.get("web_search", "capitale de la France") == ["Paris"]
            assert reader.hits == 1
        finally:
            backend_a.clear()

    async def test_entry_ttl_is_delegated_to_redis(self, redis_client: Any) -> None:
        """The TTL is enforced by the backend, not only in memory."""
        backend = RedisCacheBackend(redis_client)
        store = CacheStore(l1_backend=backend)
        key = f"{backend._prefix}:{make_cache_key('web_search', 'expiring')}"
        try:
            store.set(
                "web_search",
                "expiring",
                value="fresh",
                ttl_seconds=30,
                source_freshness=datetime.now(UTC),
            )

            assert store.get("web_search", "expiring") == "fresh"
            assert 0 < redis_client.ttl(key) <= 30

            redis_client.delete(key)

            assert store.get("web_search", "expiring") is None
            assert store.misses == 1
        finally:
            backend.clear()

    async def test_entry_without_freshness_is_not_reused(self, redis_client: Any) -> None:
        """§41.5 — an entry with no freshness metadata is never reused."""
        backend = RedisCacheBackend(redis_client)
        store = CacheStore(l1_backend=backend)
        try:
            store.set("web_search", "undated", value=["Paris"])

            assert store.get("web_search", "undated") is None
            assert store.stale_rejections == 1
        finally:
            backend.clear()

    async def test_stale_entry_is_dropped_from_redis(self, redis_client: Any) -> None:
        """§41.5 — a source older than the threshold is evicted, not served."""
        backend = RedisCacheBackend(redis_client)
        store = CacheStore(l1_backend=backend)
        backend_key = f"{backend._prefix}:{make_cache_key('web_search', 'stale')}"
        try:
            store.set(
                "web_search",
                "stale",
                value=["outdated"],
                source_freshness=datetime.now(UTC) - timedelta(hours=48),
            )

            assert store.get("web_search", "stale") is None
            assert store.stale_rejections == 1
            assert redis_client.get(backend_key) is None
        finally:
            backend.clear()

    async def test_invalidation_drops_only_the_targeted_source(self, redis_client: Any) -> None:
        """§41.5 — invalidating one source leaves the other entries usable."""
        backend = RedisCacheBackend(redis_client)
        store = CacheStore(l1_backend=backend)
        fresh = datetime.now(UTC)
        try:
            store.set(
                "web_search",
                "paris",
                value=["Paris"],
                source_id="SRC_A",
                source_freshness=fresh,
            )
            store.set(
                "web_search", "berlin", value=["Berlin"], source_id="SRC_B", source_freshness=fresh
            )

            dropped = store.invalidate_source("SRC_A")

            assert dropped == 1
            assert store.get("web_search", "paris") is None
            assert store.get("web_search", "berlin") == ["Berlin"]
        finally:
            backend.clear()

    async def test_l2_can_be_pointed_at_redis(self, redis_client: Any) -> None:
        """L1 and L2 are independently selectable backends (§41.5)."""
        l1 = RedisCacheBackend(redis_client, prefix="inis:test:l1")
        l2 = RedisCacheBackend(redis_client, prefix="inis:test:l2")
        store = CacheStore(l1_backend=l1, l2_backend=l2)
        try:
            store.set(
                "information_unit",
                "INF_1",
                value={"text": "Paris"},
                level=L2,
                source_freshness=datetime.now(UTC),
            )

            assert store.get("information_unit", "INF_1", level=L2) == {"text": "Paris"}
            assert store.get("information_unit", "INF_1", level=L1) is None
        finally:
            l1.clear()
            l2.clear()

