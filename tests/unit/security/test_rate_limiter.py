"""Tests for rate limiting per INIS §19."""

import asyncio
import time

import pytest

from app.core.errors import ValidationError
from app.security.rate_limiting import RateLimiter, RateLimitStore


async def test_rate_limiter_allow_request():
    """Test rate limiter allows request within limit."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    allowed, remaining = await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is True
    assert remaining >= 0
    assert remaining < 10


async def test_rate_limiter_deny_request():
    """Test rate limiter denies request when limit exceeded."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    allowed, remaining = await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is False
    assert remaining < 1.0


async def test_rate_limiter_refill():
    """Test rate limiter refills tokens over time."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        await limiter.is_allowed("user1", capacity=10, refill_rate=10.0)

    await asyncio.sleep(0.2)

    allowed, _ = await limiter.is_allowed("user1", capacity=10, refill_rate=10.0)

    assert allowed is True


async def test_rate_limiter_different_keys():
    """Test rate limiter handles different keys independently."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    allowed1, _ = await limiter.is_allowed("user1", capacity=5, refill_rate=1.0)
    allowed2, _ = await limiter.is_allowed("user2", capacity=5, refill_rate=1.0)

    assert allowed1 is True
    assert allowed2 is True


async def test_rate_limiter_get_wait_time():
    """Test getting wait time for next token."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    wait_time = await limiter.get_wait_time("user1", refill_rate=1.0)

    assert wait_time > 0


async def test_rate_limiter_reset():
    """Test resetting rate limit for a key."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    await limiter.reset("user1")

    allowed, _ = await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is True
    allowed2, _ = await limiter.is_allowed("user1", capacity=10, refill_rate=1.0)
    assert allowed2 is True


async def test_rate_limiter_rejects_invalid_arguments():
    """Whatever the backend, §19 limits stay bounded and explicit."""
    limiter = RateLimiter()

    with pytest.raises(ValidationError):
        await limiter.is_allowed("", capacity=1, refill_rate=1.0)
    with pytest.raises(ValidationError):
        await limiter.is_allowed("user1", capacity=0, refill_rate=1.0)
    with pytest.raises(ValidationError):
        await limiter.is_allowed("user1", capacity=1, refill_rate=0.0)
    with pytest.raises(ValidationError):
        await limiter.get_wait_time("user1", refill_rate=0.0)


async def test_rate_limiter_wait_time_is_zero_for_untouched_bucket():
    """An untouched bucket is full, so no client should be told to wait."""
    limiter = RateLimiter()

    assert await limiter.get_wait_time("fresh-key", refill_rate=1.0) == 0.0


async def test_rate_limiter_from_env_is_process_local_without_redis_url(monkeypatch):
    """Without REDIS_URL the limiter does not require the optional redis package."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    limiter = RateLimiter.from_env()

    assert limiter.store.backend == "memory"
    assert isinstance(limiter.store, RateLimitStore)
    await limiter.aclose()


async def test_rate_limiter_reset_restores_capacity_and_aclose_is_idempotent():
    """reset() drops the bucket; aclose() safely releases an in-memory store."""
    limiter = RateLimiter()

    for _ in range(5):
        await limiter.is_allowed("user1", capacity=5, refill_rate=0.0001)
    await limiter.reset("user1")
    await limiter.aclose()

    allowed, remaining = await limiter.is_allowed("user1", capacity=5, refill_rate=0.0001)

    assert allowed is True
    assert remaining == pytest.approx(4.0, abs=0.01)
    assert time.time() > 0.0

