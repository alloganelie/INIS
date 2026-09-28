"""Rate limiter per INIS §19.

The limiter is asynchronous, like the rest of the INIS I/O layer, and delegates
the atomic refill-and-spend to its store (:class:`RateLimitStore` in memory,
``RedisRateLimitStore`` across replicas).
"""

from __future__ import annotations

from app.core.errors import ValidationError
from app.security.rate_limiting.rate_limit_store import (
    RateLimitBackend,
    RateLimitStore,
    create_rate_limit_store,
)


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, rate_limit_store: RateLimitBackend | None = None) -> None:
        """Initialize rate limiter.

        Args:
            rate_limit_store: Optional rate limit store (creates default if not provided)
        """
        self.store: RateLimitBackend = rate_limit_store or RateLimitStore()

    @classmethod
    def from_env(cls, redis_url: str | None = None) -> RateLimiter:
        """Build a limiter on the store configured by ``REDIS_URL`` (§19).

        Args:
            redis_url: Explicit Redis endpoint; defaults to ``REDIS_URL``.

        Returns:
            A limiter backed by Redis when an endpoint is configured, otherwise a
            process-local :class:`RateLimitStore`.
        """
        return cls(create_rate_limit_store(redis_url))

    async def is_allowed(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
    ) -> tuple[bool, float]:
        """Check if request is allowed under rate limit.

        Args:
            key: Identifier for the rate limit bucket (e.g., user_id, IP address)
            capacity: Maximum number of tokens in the bucket
            refill_rate: Tokens per second refill rate

        Returns:
            Tuple of (is_allowed, tokens_remaining)
        """
        return await self.store.consume(key, capacity, refill_rate)

    async def get_wait_time(self, key: str, refill_rate: float) -> float:
        """Get wait time until next token is available.

        Args:
            key: Identifier for the rate limit bucket
            refill_rate: Tokens per second refill rate

        Returns:
            Seconds to wait until next token is available

        Raises:
            ValidationError: If *refill_rate* is not strictly positive.
        """
        if refill_rate <= 0:
            raise ValidationError("refill_rate must be > 0")
        tokens, last_refill_time = await self.store.get_bucket(key)
        if last_refill_time <= 0.0 or tokens >= 1.0:
            return 0.0
        return (1.0 - tokens) / refill_rate

    async def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Args:
            key: Identifier for the rate limit bucket to reset
        """
        await self.store.remove_bucket(key)

    async def aclose(self) -> None:
        """Release the store resources (Redis connections, when applicable)."""
        await self.store.aclose()

