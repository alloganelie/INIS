"""Tests for the Redis-backed rate limit store per INIS §19."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import InfrastructureError, ValidationError
from app.security.rate_limiting import RedisRateLimitStore
from app.security.rate_limiting.redis_rate_limit_store import DEFAULT_REDIS_TTL_SECONDS


class FakeRedisClient:
    """Minimal redis.asyncio surface used by the store (duck-typed)."""

    def __init__(
        self,
        *,
        eval_result: Any = None,
        bucket: dict[Any, Any] | None = None,
        keys: list[str] | None = None,
        fail: str | None = None,
    ) -> None:
        self.eval_calls: list[tuple[Any, ...]] = []
        self.hgetall_calls: list[str] = []
        self.hset_calls: list[tuple[str, dict[str, float]]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.delete_calls: list[tuple[str, ...]] = []
        self._eval_result = eval_result if eval_result is not None else [1, "9.0"]
        self._bucket = bucket or {}
        self._keys = keys or []
        self._fail = fail

    def _maybe_fail(self, operation: str) -> None:
        if self._fail == operation:
            raise ConnectionError(f"{operation} unavailable")

    async def eval(self, *args: Any) -> Any:
        self._maybe_fail("eval")
        self.eval_calls.append(args)
        return self._eval_result

    async def hgetall(self, key: str) -> dict[Any, Any]:
        self._maybe_fail("hgetall")
        self.hgetall_calls.append(key)
        return self._bucket

    async def hset(self, key: str, mapping: dict[str, float]) -> int:
        self._maybe_fail("hset")
        self.hset_calls.append((key, mapping))
        return len(mapping)

    async def expire(self, key: str, ttl: int) -> bool:
        self._maybe_fail("expire")
        self.expire_calls.append((key, ttl))
        return True

    async def delete(self, *keys: str) -> int:
        self._maybe_fail("delete")
        self.delete_calls.append(keys)
        return len(keys)

    async def scan_iter(self, match: str | None = None) -> Any:
        self._maybe_fail("scan_iter")
        for key in self._keys:
            yield key


async def test_consume_uses_the_atomic_script_on_a_namespaced_key() -> None:
    """The read-modify-write runs inside Redis, on the INIS namespaced key."""
    client = FakeRedisClient(eval_result=[1, b"9.0"])
    store = RedisRateLimitStore(client)

    allowed, remaining = await store.consume("user-1", capacity=10, refill_rate=1.0)

    script, numkeys, key, capacity, refill_rate, now, cost = client.eval_calls[0]
    assert "redis.call('HSET'" in script
    assert "redis.call('EXPIRE'" in script
    assert numkeys == 1
    assert key == "inis:ratelimit:user-1"
    assert (capacity, refill_rate, cost) == (10, 1.0, 1.0)
    assert now > 0
    assert (allowed, remaining) == (True, 9.0)


async def test_consume_reports_denied_requests() -> None:
    """A refused spend returns ``(False, remaining)``."""
    store = RedisRateLimitStore(FakeRedisClient(eval_result=["0", "0.25"]))

    assert await store.consume("user-1", capacity=10, refill_rate=1.0) == (False, 0.25)


async def test_consume_surfaces_redis_failures() -> None:
    """Redis outages must not silently allow every request."""
    store = RedisRateLimitStore(FakeRedisClient(fail="eval"))

    with pytest.raises(InfrastructureError, match="consume failed"):
        await store.consume("user-1", capacity=1, refill_rate=1.0)


async def test_get_bucket_decodes_bytes_and_missing_payloads() -> None:
    """HGETALL payloads may be decoded (``str``) or raw (``bytes``)."""
    decoded = RedisRateLimitStore(
        FakeRedisClient(bucket={b"tokens": b"3.5", b"ts": b"1700000000.5"})
    )
    assert await decoded.get_bucket("user-1") == (3.5, 1700000000.5)

    empty = RedisRateLimitStore(FakeRedisClient(bucket={}))
    assert await empty.get_bucket("user-1") == (0.0, 0.0)


async def test_set_bucket_writes_a_hashed_bucket_with_ttl() -> None:
    """Explicit writes default to DEFAULT_REDIS_TTL_SECONDS and honour overrides."""
    client = FakeRedisClient()
    store = RedisRateLimitStore(client)

    await store.set_bucket("user-1", 4.0, 1700000000.0)
    await store.set_bucket("user-2", 1.0, 1700000000.0, ttl_seconds=30)

    assert client.hset_calls[0][0] == "inis:ratelimit:user-1"
    assert client.hset_calls[0][1] == {"tokens": 4.0, "ts": 1700000000.0}
    assert client.expire_calls == [
        ("inis:ratelimit:user-1", DEFAULT_REDIS_TTL_SECONDS),
        ("inis:ratelimit:user-2", 30),
    ]

    with pytest.raises(ValidationError):
        await store.set_bucket("user-1", 1.0, 0.0, ttl_seconds=0)


async def test_remove_bucket_and_clear_all_target_namespaced_keys() -> None:
    """Deletions never touch keys outside the configured prefix."""
    client = FakeRedisClient(keys=["inis:ratelimit:user-1", "inis:ratelimit:user-2"])
    store = RedisRateLimitStore(client)

    await store.remove_bucket("user-1")
    await store.clear_all()

    assert client.delete_calls == [
        ("inis:ratelimit:user-1",),
        ("inis:ratelimit:user-1", "inis:ratelimit:user-2"),
    ]


async def test_peek_refills_the_stored_bucket_without_writing() -> None:
    """peek() is read-only: no HSET, no expiry refresh."""
    client = FakeRedisClient(bucket={b"tokens": b"2.0", b"ts": b"1.0"})
    store = RedisRateLimitStore(client)

    tokens = await store.peek("user-1", capacity=10, refill_rate=0.5)

    assert tokens == pytest.approx(9.0, abs=1.0)
    assert client.hset_calls == []
    assert client.expire_calls == []


def test_constructor_requires_an_eval_capable_client_and_a_prefix() -> None:
    """An incomplete client or an empty prefix is a programming error."""
    with pytest.raises(ValidationError, match="eval"):
        RedisRateLimitStore(object())
    with pytest.raises(ValidationError, match="prefix"):
        RedisRateLimitStore(FakeRedisClient(), prefix="")


async def test_aclose_closes_the_client_when_supported() -> None:
    """Connections are released on shutdown, with or without ``aclose``."""

    class ClosingClient(FakeRedisClient):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    client = ClosingClient()
    await RedisRateLimitStore(client).aclose()
    assert client.closed is True

    class LegacyClient(FakeRedisClient):
        closed = False

        async def close(self) -> None:
            self.closed = True

    legacy = LegacyClient()
    await RedisRateLimitStore(legacy).aclose()
    assert legacy.closed is True
