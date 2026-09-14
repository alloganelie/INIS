"""Rate limit store per INIS §19."""

import time
from typing import Dict, Tuple


class RateLimitStore:
    """In-memory store for rate limiting using token bucket algorithm."""

    def __init__(self):
        """Initialize rate limit store."""
        self.buckets: Dict[str, Tuple[float, float]] = {}

    def get_bucket(self, key: str) -> Tuple[float, float]:
        """Get token bucket for a key.

        Args:
            key: Identifier for the bucket (e.g., user_id, IP address)

        Returns:
            Tuple of (tokens, last_refill_time)
        """
        return self.buckets.get(key, (0.0, 0.0))

    def set_bucket(self, key: str, tokens: float, last_refill_time: float) -> None:
        """Set token bucket for a key.

        Args:
            key: Identifier for the bucket
            tokens: Current token count
            last_refill_time: Last refill timestamp
        """
        self.buckets[key] = (tokens, last_refill_time)

    def remove_bucket(self, key: str) -> None:
        """Remove token bucket for a key.

        Args:
            key: Identifier for the bucket to remove
        """
        self.buckets.pop(key, None)

    def clear_all(self) -> None:
        """Clear all buckets."""
        self.buckets.clear()
