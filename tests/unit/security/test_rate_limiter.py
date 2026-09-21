"""Tests for rate limiting per INIS §19."""

import time

import pytest

from app.security.rate_limiting import RateLimiter, RateLimitStore


def test_rate_limiter_allow_request():
    """Test rate limiter allows request within limit."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    allowed, remaining = limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is True
    assert remaining >= 0
    assert remaining < 10


def test_rate_limiter_deny_request():
    """Test rate limiter denies request when limit exceeded."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    allowed, remaining = limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is False
    assert remaining < 1.0


def test_rate_limiter_refill():
    """Test rate limiter refills tokens over time."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        limiter.is_allowed("user1", capacity=10, refill_rate=10.0)

    time.sleep(0.2)

    allowed, remaining = limiter.is_allowed("user1", capacity=10, refill_rate=10.0)

    assert allowed is True


def test_rate_limiter_different_keys():
    """Test rate limiter handles different keys independently."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    allowed1, _ = limiter.is_allowed("user1", capacity=5, refill_rate=1.0)
    allowed2, _ = limiter.is_allowed("user2", capacity=5, refill_rate=1.0)

    assert allowed1 is True
    assert allowed2 is True


def test_rate_limiter_get_wait_time():
    """Test getting wait time for next token."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    wait_time = limiter.get_wait_time("user1", refill_rate=1.0)

    assert wait_time > 0


def test_rate_limiter_reset():
    """Test resetting rate limit for a key."""
    store = RateLimitStore()
    limiter = RateLimiter(store)

    for _ in range(10):
        limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    limiter.reset("user1")

    allowed, _ = limiter.is_allowed("user1", capacity=10, refill_rate=1.0)

    assert allowed is True
    allowed2, _ = limiter.is_allowed("user1", capacity=10, refill_rate=1.0)
    assert allowed2 is True
