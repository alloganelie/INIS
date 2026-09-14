"""Rate limiter per INIS §19."""

import time

from app.security.rate_limiting.rate_limit_store import RateLimitStore


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, rate_limit_store: RateLimitStore | None = None):
        """Initialize rate limiter.

        Args:
            rate_limit_store: Optional rate limit store (creates default if not provided)
        """
        self.store = rate_limit_store or RateLimitStore()

    def is_allowed(self, key: str, capacity: int, refill_rate: float) -> tuple[bool, float]:
        """Check if request is allowed under rate limit.

        Args:
            key: Identifier for the rate limit bucket (e.g., user_id, IP address)
            capacity: Maximum number of tokens in the bucket
            refill_rate: Tokens per second refill rate

        Returns:
            Tuple of (is_allowed, tokens_remaining)
        """
        current_time = time.time()
        tokens, last_refill_time = self.store.get_bucket(key)

        if last_refill_time == 0:
            tokens = float(capacity)
        else:
            time_elapsed = current_time - last_refill_time
            tokens = min(capacity, tokens + time_elapsed * refill_rate)

        if tokens >= 1.0:
            tokens -= 1.0
            self.store.set_bucket(key, tokens, current_time)
            return True, tokens

        self.store.set_bucket(key, tokens, current_time)
        return False, tokens

    def get_wait_time(self, key: str, refill_rate: float) -> float:
        """Get wait time until next token is available.

        Args:
            key: Identifier for the rate limit bucket
            refill_rate: Tokens per second refill rate

        Returns:
            Seconds to wait until next token is available
        """
        tokens, _ = self.store.get_bucket(key)

        if tokens >= 1.0:
            return 0.0

        return (1.0 - tokens) / refill_rate

    def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Args:
            key: Identifier for the rate limit bucket to reset
        """
        self.store.remove_bucket(key)
