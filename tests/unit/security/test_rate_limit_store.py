"""Tests for rate limit stores (in-memory backend and environment selection)."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from app.core.errors import InfrastructureError, ValidationError
from app.security.rate_limiting import (
    RateLimitStore,
    RedisRateLimitStore,
    create_rate_limit_store,
)
from app.security.rate_limiting.rate_limit_store import refilled_tokens


async def test_consume_is_atomic_under_concurrency() -> None:
    """20 concurrent spends on a capacity-5 bucket allow exactly 5 requests."""
    store = RateLimitStore()

    results = await asyncio.gather(
        *(store.consume("user-1", capacity=5, refill_rate=0.0001) for _ in range(20))
    )

    assert sum(1 for allowed, _ in results if allowed) == 5
    assert all(remaining >= 0.0 for _, remaining in results)


async def test_bucket_roundtrip_and_clear() -> None:
    """Unseen keys read as empty and clear_all() drops every bucket."""
    store = RateLimitStore()

    assert await store.get_bucket("user-1") == (0.0, 0.0)
    await store.set_bucket("user-1", 2.5, 123.0)
    assert await store.get_bucket("user-1") == (2.5, 123.0)

    await store.clear_all()

    assert await store.get_bucket("user-1") == (0.0, 0.0)


async def test_peek_refills_without_spending() -> None:
    """peek() reports a full bucket for unseen keys and never consumes tokens."""
    store = RateLimitStore()

    assert await store.peek("user-1", capacity=5, refill_rate=1.0) == 5.0

    await store.consume("user-1", capacity=5, refill_rate=0.0001)

    assert await store.peek("user-1", capacity=5, refill_rate=1.0) == pytest.approx(4.0, abs=0.01)
    tokens, last_refill = await store.get_bucket("user-1")
    assert tokens == pytest.approx(4.0, abs=0.01)
    assert last_refill > 0.0


async def test_set_bucket_accepts_ttl_for_interface_parity() -> None:
    """The in-memory backend ignores ttl_seconds (idle buckets simply refill)."""
    store = RateLimitStore()

    await store.set_bucket("user-1", 1.0, 0.0, ttl_seconds=1)

    assert await store.get_bucket("user-1") == (1.0, 0.0)


async def test_invalid_parameters_are_rejected() -> None:
    """Empty keys and non-positive limits raise ValidationError (§19)."""
    store = RateLimitStore()

    with pytest.raises(ValidationError):
        await store.consume("", capacity=1, refill_rate=1.0)
    with pytest.raises(ValidationError):
        await store.consume("user-1", capacity=0, refill_rate=1.0)
    with pytest.raises(ValidationError):
        await store.consume("user-1", capacity=1, refill_rate=0.0)
    with pytest.raises(ValidationError):
        await store.peek("user-1", capacity=1, refill_rate=0.0)


def test_refilled_tokens_starts_full_caps_and_ignores_clock_skew() -> None:
    """Refill maths are shared by both backends."""
    assert refilled_tokens(0.0, 0.0, 10, 1.0, 1000.0) == 10.0
    assert refilled_tokens(2.0, 100.0, 10, 1.0, 100.5) == 2.5
    assert refilled_tokens(2.0, 100.0, 10, 1.0, 100.5) <= 10.0
    assert refilled_tokens(2.0, 100.0, 10, 1.0, 90.0) == 2.0


async def test_create_rate_limit_store_defaults_to_process_local(monkeypatch) -> None:
    """Without REDIS_URL there is no dependency on the optional redis package."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    store = create_rate_limit_store()

    assert isinstance(store, RateLimitStore)
    assert store.backend == "memory"


async def test_create_rate_limit_store_fails_loudly_without_redis_package(monkeypatch) -> None:
    """A configured REDIS_URL without the optional client must not degrade silently."""
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setitem(sys.modules, "redis", None)

    with pytest.raises(InfrastructureError, match="REDIS_URL"):
        create_rate_limit_store()


async def test_create_rate_limit_store_builds_redis_backend(monkeypatch) -> None:
    """A redis.asyncio-compatible module is enough to select the shared backend."""
    urls: list[str] = []

    class FakeClient:
        """Minimal client the store constructor accepts (needs eval)."""

        async def eval(self, *args: object) -> list[object]:  # pragma: no cover - not called
            return [1, "1.0"]

    fake_asyncio = types.ModuleType("redis.asyncio")

    def from_url(url: str) -> FakeClient:
        urls.append(url)
        return FakeClient()

    fake_asyncio.from_url = from_url  # type: ignore[attr-defined]
    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = fake_asyncio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis)

    store = create_rate_limit_store("redis://cache:6379/0")

    assert isinstance(store, RedisRateLimitStore)
    assert store.backend == "redis"
    assert urls == ["redis://cache:6379/0"]
