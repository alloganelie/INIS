"""Rate limit stores per INIS §19.

Two interchangeable backends expose the same asynchronous API:

* :class:`RateLimitStore` — process-local token buckets guarded by an
  :class:`asyncio.Lock`; the default for single-process deployments (and tests).
* :class:`~app.security.rate_limiting.redis_rate_limit_store.RedisRateLimitStore`
  — buckets shared across replicas, backed by any ``redis.asyncio``-compatible
  client (see :func:`create_rate_limit_store`).

Only :meth:`RateLimitStore.consume` must be atomic: a ``get_bucket()`` followed by
a ``set_bucket()`` performed by two concurrent callers would let a burst exceed
``capacity``. The primitive accessors stay public for inspection, custom backends
and administrative resets.

``redis`` is an optional dependency: :func:`create_rate_limit_store` imports it
lazily, and only when ``REDIS_URL`` is configured.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Protocol

from app.core.errors import InfrastructureError, ValidationError

#: Prefix applied to every Redis key so INIS buckets never collide.
DEFAULT_REDIS_PREFIX = "inis:ratelimit:"


class RateLimitBackend(Protocol):
    """Asynchronous token bucket backend consumed by ``RateLimiter``."""

    backend: str

    async def get_bucket(self, key: str) -> tuple[float, float]:
        """Return ``(tokens, last_refill_time)`` for *key*."""
        ...

    async def set_bucket(
        self,
        key: str,
        tokens: float,
        last_refill_time: float,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store the token bucket of *key*."""
        ...

    async def remove_bucket(self, key: str) -> None:
        """Drop the token bucket of *key*."""
        ...

    async def clear_all(self) -> None:
        """Drop every token bucket."""
        ...

    async def peek(self, key: str, capacity: float, refill_rate: float) -> float:
        """Return the refilled token count of *key* without spending a token."""
        ...

    async def consume(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        cost: float = 1.0,
    ) -> tuple[bool, float]:
        """Atomically refill and spend *cost* tokens; return ``(allowed, tokens)``."""
        ...

    async def aclose(self) -> None:
        """Release backend resources (no-op for the in-memory store)."""
        ...


def validate_key(key: str) -> None:
    """Reject empty bucket identifiers (they would share one global bucket)."""
    if not key or not isinstance(key, str):
        raise ValidationError("key must be a non-empty string")


def validate_request(capacity: float, refill_rate: float, cost: float = 1.0) -> None:
    """Validate the token bucket parameters shared by every backend."""
    if capacity <= 0:
        raise ValidationError("capacity must be > 0")
    if refill_rate <= 0:
        raise ValidationError("refill_rate must be > 0")
    if cost <= 0:
        raise ValidationError("cost must be > 0")


def refilled_tokens(
    tokens: float,
    last_refill_time: float,
    capacity: float,
    refill_rate: float,
    now: float,
) -> float:
    """Return the token count after refill, capped at *capacity*.

    A bucket that was never written (``last_refill_time <= 0``) starts full, which
    matches the historical behaviour of the token bucket limiter.
    """
    if last_refill_time <= 0.0:
        return float(capacity)
    return min(float(capacity), float(tokens) + max(0.0, now - last_refill_time) * refill_rate)


def as_float(value: Any) -> float:
    """Decode a Redis payload value (``bytes``, ``str``, ``int`` or ``float``)."""
    if value is None:
        return 0.0
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class RateLimitStore:
    """In-memory token bucket store (single process, lock-guarded)."""

    backend = "memory"

    def __init__(self) -> None:
        """Initialize rate limit store."""
        self.buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def get_bucket(self, key: str) -> tuple[float, float]:
        """Get token bucket for a key.

        Args:
            key: Identifier for the bucket (e.g., user_id, IP address)

        Returns:
            Tuple of (tokens, last_refill_time)
        """
        async with self._lock:
            return self.buckets.get(key, (0.0, 0.0))

    async def set_bucket(
        self,
        key: str,
        tokens: float,
        last_refill_time: float,
        ttl_seconds: int | None = None,
    ) -> None:
        """Set token bucket for a key.

        Args:
            key: Identifier for the bucket
            tokens: Current token count
            last_refill_time: Last refill timestamp
            ttl_seconds: Ignored here — an idle in-memory bucket refills to its
                capacity, which is equivalent to a Redis key expiry.
        """
        async with self._lock:
            self.buckets[key] = (float(tokens), float(last_refill_time))

    async def remove_bucket(self, key: str) -> None:
        """Remove token bucket for a key.

        Args:
            key: Identifier for the bucket to remove
        """
        async with self._lock:
            self.buckets.pop(key, None)

    async def clear_all(self) -> None:
        """Clear all buckets."""
        async with self._lock:
            self.buckets.clear()

    async def peek(self, key: str, capacity: float, refill_rate: float) -> float:
        """Return the refilled token count without spending a token."""
        validate_request(capacity, refill_rate)
        tokens, last_refill_time = await self.get_bucket(key)
        return refilled_tokens(tokens, last_refill_time, capacity, refill_rate, time.time())

    async def consume(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
        cost: float = 1.0,
    ) -> tuple[bool, float]:
        """Atomically refill then spend *cost* tokens.

        Returns:
            Tuple of (is_allowed, tokens_remaining)
        """
        validate_key(key)
        validate_request(capacity, refill_rate, cost)
        now = time.time()
        async with self._lock:
            tokens, last_refill_time = self.buckets.get(key, (0.0, 0.0))
            tokens = refilled_tokens(tokens, last_refill_time, capacity, refill_rate, now)
            allowed = tokens >= cost
            if allowed:
                tokens -= cost
            self.buckets[key] = (tokens, now)
            return allowed, tokens

    async def aclose(self) -> None:
        """Release backend resources (nothing to release in memory)."""
        return


def create_rate_limit_store(redis_url: str | None = None) -> RateLimitBackend:
    """Return the rate limit store selected by the environment.

    Args:
        redis_url: Explicit Redis endpoint; defaults to ``REDIS_URL``.

    Returns:
        A ``RedisRateLimitStore`` when an endpoint is configured, otherwise the
        process-local :class:`RateLimitStore`.

    Raises:
        InfrastructureError: If an endpoint is configured but the optional
            ``redis`` package is missing or the URL cannot be used. Failing loudly
            prevents a multi-replica deployment from silently falling back to
            per-process limits (§19).
    """
    url = redis_url or os.getenv("REDIS_URL")
    if not url:
        return RateLimitStore()
    try:
        from redis import asyncio as redis_asyncio
    except ImportError as exc:
        raise InfrastructureError(
            "REDIS_URL is configured but the optional 'redis' package is not installed; "
            "install 'redis' or unset REDIS_URL to use per-process rate limits"
        ) from exc
    try:
        client = redis_asyncio.from_url(url)
    except Exception as exc:
        raise InfrastructureError(f"unable to build a Redis client from REDIS_URL: {exc}") from exc
    from app.security.rate_limiting.redis_rate_limit_store import RedisRateLimitStore

    return RedisRateLimitStore(client)
