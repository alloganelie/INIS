"""Tests for the §19 rate limit middleware (B4-bis constat 4).

Acceptance criteria:
- test_rate_limit_middleware_returns_429
- test_rate_limit_keyed_by_actor_id
- test_rate_limit_exempts_health_docs
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.rate_limit_middleware import RateLimitMiddleware
from app.security.rate_limiting.rate_limiter import RateLimiter
from app.security.rate_limiting.rate_limit_store import RateLimitStore


def _fresh_limiter() -> RateLimiter:
    return RateLimiter(RateLimitStore())


def _build_client(rpm: int) -> TestClient:
    """Build a tiny app with a fresh limiter and the rate limit middleware."""
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=rpm,
        limiter=_fresh_limiter(),
    )

    @app.get("/v1/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INIS_RATE_LIMIT_ENABLED", "true")
    monkeypatch.delenv("RATE_LIMIT_RPM", raising=False)


def test_rate_limit_middleware_returns_429() -> None:
    """The N+1-th request inside the window gets 429 + Retry-After."""
    client = _build_client(2)

    assert client.get("/v1/ping").status_code == 200
    assert client.get("/v1/ping").status_code == 200

    limited = client.get("/v1/ping")
    assert limited.status_code == 429
    assert limited.json()["detail"] == "Rate limit exceeded"
    assert limited.json()["limit"] == 2
    assert int(limited.headers["Retry-After"]) >= 1


def test_rate_limit_keyed_by_actor_id() -> None:
    """Two different actors have independent budgets; one actor exhausts his."""
    app = FastAPI()

    # The limiter is added FIRST so the fake auth (outer) resolves the actor
    # before the bucket key is computed - same ordering as app/main.py.
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=1,
        limiter=_fresh_limiter(),
    )

    @app.middleware("http")
    async def fake_auth(request: Any, call_next: Any) -> Any:
        request.state.actor_id = request.headers.get("x-actor", "anonymous_actor")
        return await call_next(request)

    @app.get("/v1/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    client = TestClient(app)

    # actor-a spends its single token, then is limited...
    assert client.get("/v1/ping", headers={"x-actor": "actor-a"}).status_code == 200
    assert client.get("/v1/ping", headers={"x-actor": "actor-a"}).status_code == 429
    # ...while actor-b still has its own untouched budget.
    assert client.get("/v1/ping", headers={"x-actor": "actor-b"}).status_code == 200


def test_rate_limit_exempts_health_docs() -> None:
    """Health and docs paths are never metered, whatever the budget."""
    client = _build_client(1)

    for _ in range(5):
        assert client.get("/health").status_code == 200
    # The single token is still available for a metered path.
    assert client.get("/v1/ping").status_code == 200


def test_rate_limit_is_inert_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without configuration the middleware must not meter anything."""
    monkeypatch.delenv("INIS_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("RATE_LIMIT_RPM", raising=False)

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware, requests_per_minute=1, limiter=_fresh_limiter()
    )

    @app.get("/v1/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    client = TestClient(app)
    for _ in range(5):
        assert client.get("/v1/ping").status_code == 200


def test_rate_limit_middleware_is_wired_on_the_app() -> None:
    """app.main mounts the middleware, inside AuthMiddleware (§19)."""
    from app.api.middleware.auth_middleware import AuthMiddleware
    from app.main import app as inis_app

    mounted = [m.cls for m in inis_app.user_middleware]
    assert RateLimitMiddleware in mounted
    # Auth must be outer (earlier index) so the limiter sees request.state.actor_id.
    assert mounted.index(AuthMiddleware) < mounted.index(RateLimitMiddleware)
