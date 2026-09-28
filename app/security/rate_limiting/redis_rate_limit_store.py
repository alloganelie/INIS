"""Redis-backed rate limit store per INIS §19.

The store is duck-typed on any ``redis.asyncio``-compatible client (``eval``,
``hgetall``, ``hset``, ``expire``, ``delete``, ``scan_iter``): INIS keeps
``redis`` as an optional dependency and this backend stays testable with a fake.

Why a Lua script: a token bucket is a read-modify-write. Executed in Python
(``get_bucket`` then ``set_bucket``), two replicas could both read the same
token count and both allow the request, exceeding ``capacity``. The script runs
the whole refill-and-spend step inside Redis, so the limit holds across replicas.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.errors import InfrastructureError, ValidationError
from app.security.rate_limiting.rate_limit_store import (
    DEFAULT_REDIS_PREFIX,
    as_float,
    refilled_tokens,
    validate_key,
    validate_request,
)

#: TTL applied by :meth:`RedisRateLimitStore.set_bucket` (explicit writes only).
DEFAULT_REDIS_TTL_SECONDS = 3600

#: Atomic token bucket: refill, spend ``cost`` tokens, persist and expire.
#: KEYS[1] = bucket key. ARGV = capacity, refill_rate, now, cost.
_CONSUME_SCRIPT = """
local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])
if tokens == nil or last_refill == nil then
  tokens = capacity
  last_refill = now
end
local elapsed = now - last_refill
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_rate)
local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill_rate) + 1)
return {allowed, tostring(tokens)}
"""


class RedisRateLimitStore:
    """Shared token bucket store backed by a Redis client."""

    backend = "redis"

    def __init__(self, client: Any, *, prefix: str = DEFAULT_REDIS_PREFIX) -> None:
        """Initialize the Redis-backed store.

        Args:
            client: Asynchronous Redis client (``redis.asyncio.Redis``).
            prefix: Key namespace; every bucket is stored as ``<prefix><key>``.

        Raises:
            ValidationError: If the client cannot run Lua scripts or the prefix is
                empty.
        """
        if client is None or not callable(getattr(client, "eval", None)):
            raise ValidationError("client must expose an async eval() method")
        if not prefix or not isinstance(prefix, str):
            raise ValidationError("prefix must be a non-empty string")
        self.client = client
        self.prefix = prefix

    def _key(self, key: str) -> str:
        """Return the namespaced Redis key of *key*."""
        validate_key(key)
        return f"{self.prefix}{key}"

    @staticmethod
    def _decode_bucket(payload: Any) -> tuple[float, float]:
        """Decode an ``HGETALL`` payload into ``(tokens, last_refill_time)``."""
        if not payload:
            return (0.0, 0.0)
        values = payload if isinstance(payload, dict) else {}
        tokens = values.get("tokens", values.get(b"tokens"))
        last_refill_time = values.get("ts", values.get(b"ts"))
        return (as_float(tokens), as_float(last_refill_time))

    async def get_bucket(self, key: str) -> tuple[float, float]:
        """Get the raw token bucket stored in Redis for a key."""
        try:
            payload = await self.client.hgetall(self._key(key))
        except Exception as exc:
            raise InfrastructureError(f"redis rate limit read failed: {exc}") from exc
        return self._decode_bucket(payload)

    async def set_bucket(
        self,
        key: str,
        tokens: float,
        last_refill_time: float,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a token bucket in Redis, with an explicit TTL.

        Args:
            key: Identifier for the bucket.
            tokens: Current token count.
            last_refill_time: Last refill timestamp.
            ttl_seconds: Key expiry; defaults to :data:`DEFAULT_REDIS_TTL_SECONDS`.
                :meth:`consume` uses a bucket-specific TTL instead (the time needed
                to refill from empty), so this only affects explicit writes.
        """
        ttl = DEFAULT_REDIS_TTL_SECONDS if ttl_seconds is None else int(ttl_seconds)
        if ttl < 1:
            raise ValidationError("ttl_seconds must be >= 1")
        redis_key = self._key(key)
        try:
            await self.client.hset(
                redis_key,
                mapping={"tokens": float(tokens), "ts": float(last_refill_time)},
            )
            await self.client.expire(redis_key, ttl)
        except Exception as exc:
            raise InfrastructureError(f"redis rate limit write failed: {exc}") from exc

    async def remove_bucket(self, key: str) -> None:
        """Delete the token bucket of a key."""
        try:
            await self.client.delete(self._key(key))
        except Exception as exc:
            raise InfrastructureError(f"redis rate limit delete failed: {exc}") from exc

    async def clear_all(self) -> None:
        """Delete every bucket under the configured prefix."""
        try:
            redis_keys = [
                redis_key async for redis_key in self.client.scan_iter(match=f"{self.prefix}*")
            ]
            if redis_keys:
                await self.client.delete(*redis_keys)
        except Exception as exc:
            raise InfrastructureError(f"redis rate limit clear failed: {exc}") from exc

    async def peek(self, key: str, capacity: float, refill_rate: float) -> float:
        """Return the refilled token count stored in Redis, without writing."""
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
        """Refill and spend tokens through one atomic Lua script.

        Returns:
            Tuple of (is_allowed, tokens_remaining).

        Raises:
            InfrastructureError: If the Redis call fails; rate limiting must fail
                loudly instead of silently allowing every request.
        """
        validate_key(key)
        validate_request(capacity, refill_rate, cost)
        try:
            result = await self.client.eval(
                _CONSUME_SCRIPT,
                1,
                self._key(key),
                capacity,
                refill_rate,
                time.time(),
                cost,
            )
        except Exception as exc:
            raise InfrastructureError(f"redis rate limit consume failed: {exc}") from exc
        allowed_raw, tokens_raw = result[0], result[1]
        return bool(int(as_float(allowed_raw))), as_float(tokens_raw)

    async def aclose(self) -> None:
        """Close the underlying Redis client when it exposes a closer."""
        closer = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
        if callable(closer):
            await closer()
