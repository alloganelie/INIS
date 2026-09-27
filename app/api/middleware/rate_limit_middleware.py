"""Rate limiting middleware per §19.

``RateLimiter`` (token bucket, §19) existed since the B4 audit but nothing in
``app/`` ever instantiated it, so the API was effectively unmetered. This
middleware mounts it on the ASGI app:

* the bucket key is the authenticated ``request.state.actor_id`` resolved by
  :class:`~app.api.middleware.auth_middleware.AuthMiddleware`; anonymous
  callers fall back to their client host so one noisy IP cannot exhaust an
  authenticated actor's budget;
* the store is Redis-backed when ``REDIS_URL`` is set (shared across replicas)
  and process-local otherwise;
* health, docs and auth-login paths are exempt, exactly like the auth
  middleware exemptions;
* an over-limit request gets ``429`` plus a ``Retry-After`` header.

Activation is explicit: the middleware is inert unless ``INIS_RATE_LIMIT_ENABLED``
is truthy or ``RATE_LIMIT_RPM`` is set. A default-on 60 rpm bucket would make
the development and test suites fail with 429s on shared anonymous keys.
"""

from __future__ import annotations

import math
import os
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.middleware.auth_middleware import EXEMPT_EXACT_PATHS, EXEMPT_PREFIXES
from app.security.rate_limiting import RateLimiter

#: Default budget: 60 requests per minute and per actor.
DEFAULT_REQUESTS_PER_MINUTE = 60

ENV_REQUESTS_PER_MINUTE = "RATE_LIMIT_RPM"
ENV_ENABLED = "INIS_RATE_LIMIT_ENABLED"

#: Bucket key used when no actor could be resolved at all.
ANONYMOUS_KEY = "anonymous"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def rate_limit_enabled() -> bool:
    """Return whether the rate limiter must actually meter requests.

    Enabled when ``INIS_RATE_LIMIT_ENABLED`` is truthy, or as soon as
    ``RATE_LIMIT_RPM`` is explicitly configured (an explicit budget is an
    explicit intent to enforce it).
    """
    if _truthy(os.getenv(ENV_ENABLED)):
        return True
    return bool(os.getenv(ENV_REQUESTS_PER_MINUTE))


def resolve_requests_per_minute() -> int:
    """Return the configured budget, falling back to the 60 rpm default."""
    raw = os.getenv(ENV_REQUESTS_PER_MINUTE)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_REQUESTS_PER_MINUTE


def is_exempt_path(path: str) -> bool:
    """Return whether *path* bypasses the limiter (health, docs, login)."""
    if path in EXEMPT_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Meter every request against a per-actor token bucket (§19).

    The limiter is created lazily on the first metered request so importing
    ``app.main`` never fails on a misconfigured ``REDIS_URL``; a Redis failure
    degrades to per-process buckets instead of taking the API down.
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._requests_per_minute = (
            requests_per_minute
            if requests_per_minute is not None
            else resolve_requests_per_minute()
        )
        self._capacity = float(self._requests_per_minute)
        self._refill_rate = self._requests_per_minute / 60.0

    @property
    def requests_per_minute(self) -> int:
        """Budget applied to each bucket."""
        return self._requests_per_minute

    def _get_limiter(self) -> RateLimiter:
        if self._limiter is None:
            try:
                self._limiter = RateLimiter.from_env()
            except Exception:  # noqa: BLE001 - Redis trouble must not kill the API
                self._limiter = RateLimiter()
        return self._limiter

    def bucket_key(self, request: Request) -> str:
        """Return the bucket identifier of *request*.

        Prefers the authenticated ``actor_id``; falls back to the client host so
        unauthenticated traffic is still metered per caller.
        """
        actor_id = getattr(request.state, "actor_id", None)
        if actor_id:
            return str(actor_id)
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"apikey:{api_key[:32]}"
        client = request.client
        if client is not None and client.host:
            return f"ip:{client.host}"
        return ANONYMOUS_KEY

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not rate_limit_enabled() or is_exempt_path(request.url.path):
            return await call_next(request)

        limiter = self._get_limiter()
        key = self.bucket_key(request)
        allowed, remaining = await limiter.is_allowed(key, self._capacity, self._refill_rate)

        if not allowed:
            retry_after = max(
                1,
                math.ceil(await limiter.get_wait_time(key, self._refill_rate)),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit": self._requests_per_minute,
                    "window": "minute",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        return response


__all__ = [
    "DEFAULT_REQUESTS_PER_MINUTE",
    "RateLimitMiddleware",
    "is_exempt_path",
    "rate_limit_enabled",
    "resolve_requests_per_minute",
]
