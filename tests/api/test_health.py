"""Tests for health and version endpoints."""

import asyncio
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _hermetic_health_env(monkeypatch: Any) -> Any:
    """Isolate readiness from ambient CI env (REDIS_URL, broker, DB, LLM).

    CI sets REDIS_URL to a live service; without isolation the "unconfigured"
    tests really ping Redis (timeout -> 503) instead of reporting
    not_configured (200). Clear optional-dep env vars and module-level probe
    caches before AND after each test so no state leaks between tests.
    Tests that need a var/probe set it explicitly in their body (runs after
    this fixture), so they still exercise the configured path.
    """
    for var in (
        "INIS_DATABASE_URL",
        "REDIS_URL",
        "AMQP_URL",
        "INIS_BROKER_URL",
        "LLM_API_KEY",
        "LLM_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    from app.api.v1.system import health_router
    from app.api.v1.sources import repository as sources_repository

    health_router._redis_probe = None
    health_router._redis_client = None
    health_router._broker_probe = None
    sources_repository._DATABASE_ENGINE = None
    sources_repository._CACHED_URL = None
    yield
    health_router._redis_probe = None
    health_router._redis_client = None
    health_router._broker_probe = None
    sources_repository._DATABASE_ENGINE = None
    sources_repository._CACHED_URL = None


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.0"


def test_version_returns_version() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "2.0.0"
    assert "commit" in data
    assert isinstance(data["commit"], str)
    assert len(data["commit"]) > 0


def test_v1_health_ready_default(monkeypatch: Any) -> None:
    """With nothing configured, readiness is degraded - never a false 'ready'."""
    # Hermetic via _hermetic_health_env: no INIS_DATABASE_URL / REDIS_URL /
    # broker / LLM key, so every optional dep reports not_configured -> 200.
    res = client.get("/v1/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "degraded"
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] == "not_configured"
    assert "broker" in data["checks"]
    assert data["checks"]["broker"]["status"] == "not_configured"


def test_v1_health_ready_with_database(monkeypatch: any) -> None:
    """Ensure GET /v1/health/ready executes SELECT 1 when INIS_DATABASE_URL is set."""
    monkeypatch.setenv("INIS_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    res = client.get("/v1/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["checks"]["database"]["status"] == "ready"
    # Broker, Redis and LLM remain unconfigured, so overall stays degraded.
    assert data["status"] == "degraded"


def test_v1_health_ready_database_failure(monkeypatch: any) -> None:
    """Ensure GET /v1/health/ready returns 503 when the database check fails."""
    monkeypatch.setenv("INIS_DATABASE_URL", "postgresql+asyncpg://invalid:5432/bad_db")
    res = client.get("/v1/health/ready")
    assert res.status_code == 503
    data = res.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["status"] == "not_ready"
    assert "error" in data["checks"]["database"]


def test_v1_health_ready_broker_states() -> None:
    """Ensure GET /v1/health/ready reflects broker connectivity."""
    from app.api.v1.system.health_router import set_broker_check

    class DummyBroker:
        def __init__(self, connected: bool) -> None:
            self.is_connected = connected

    try:
        # 1. Disconnected broker -> 503
        set_broker_check(DummyBroker(connected=False))
        res = client.get("/v1/health/ready")
        assert res.status_code == 503
        assert res.json()["status"] == "not_ready"
        assert res.json()["checks"]["broker"]["status"] == "not_ready"

        # 2. Connected broker -> 200 (overall degraded: db/redis/llm unconfigured)
        set_broker_check(DummyBroker(connected=True))
        res_ok = client.get("/v1/health/ready")
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "degraded"
        assert res_ok.json()["checks"]["broker"]["status"] == "ready"
    finally:
        set_broker_check(None)


def test_v1_health_exposes_circuit_breaker_states() -> None:
    """§41.8: /v1/health must expose open | closed | half_open per scope."""
    from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig, registry

    try:
        registry.reset(default_config=CircuitBreakerConfig(failure_threshold=1))
        breaker = registry.get("provider:serper")
        breaker.record_failure()

        # Basic health carries the raw state map.
        basic = client.get("/v1/health")
        assert basic.status_code == 200
        assert basic.json()["circuit_breakers"] == {"provider:serper": "open"}

        # Readiness reports it too, as a degraded (non-gating) check.
        res = client.get("/v1/health/ready")
        cb = res.json()["checks"]["circuit_breakers"]
        assert cb["states"] == {"provider:serper": "open"}
        assert cb["status"] == "degraded"
        # An open breaker isolates a dependency; INIS itself stays ready.
        assert res.status_code == 200
        assert res.json()["status"] == "degraded"
    finally:
        registry.reset(default_config=CircuitBreakerConfig())


def test_v1_health_ready_reports_every_wired_subsystem() -> None:
    """Readiness aggregates database, broker, redis and breaker checks (§32)."""
    res = client.get("/v1/health/ready")

    checks = res.json()["checks"]
    assert res.status_code == 200
    assert set(checks) == {"database", "broker", "redis", "llm", "circuit_breakers"}
    assert "latency_ms" in checks["database"]


def test_v1_health_ready_reports_redis_state() -> None:
    """A registered Redis client feeds the readiness report like the broker."""
    from app.api.v1.system.health_router import set_redis_check

    class DummyRedis:
        def __init__(self, up: bool) -> None:
            self._up = up

        async def ping(self) -> bool:
            if not self._up:
                raise ConnectionError("redis unreachable")
            return True

    try:
        set_redis_check(DummyRedis(up=True))
        res = client.get("/v1/health/ready")
        assert res.status_code == 200
        assert res.json()["checks"]["redis"]["status"] == "ready"

        set_redis_check(DummyRedis(up=False))
        res_down = client.get("/v1/health/ready")
        assert res_down.status_code == 503
        assert res_down.json()["checks"]["redis"]["status"] == "not_ready"
        assert "error" in res_down.json()["checks"]["redis"]
    finally:
        set_redis_check(None)


def test_v1_health_ready_redis_url_without_client_fails_loudly(
    monkeypatch: Any,
) -> None:
    """A configured REDIS_URL without the optional client is not silently ignored."""
    from app.api.v1.system import health_router

    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setitem(sys.modules, "redis", None)
    monkeypatch.setattr(health_router, "_redis_client", None)
    monkeypatch.setattr(health_router, "_redis_probe", None)

    res = client.get("/v1/health/ready")

    assert res.status_code == 503
    assert res.json()["checks"]["redis"]["status"] == "not_ready"
    assert "error" in res.json()["checks"]["redis"]


def test_v1_health_ready_isolates_failing_and_slow_checks(
    monkeypatch: Any,
) -> None:
    """A raising or hanging dependency degrades readiness without a 500."""
    from app.api.v1.system import health_router

    class ExplodingBroker:
        async def health_check(self) -> dict[str, str]:
            raise RuntimeError("broker exploded")

    class SlowBroker:
        async def health_check(self) -> dict[str, str]:
            await asyncio.sleep(5)
            return {"status": "up"}

    try:
        health_router.set_broker_check(ExplodingBroker())
        res = client.get("/v1/health/ready")
        assert res.status_code == 503
        assert res.json()["checks"]["broker"]["status"] == "not_ready"
        assert "error" in res.json()["checks"]["broker"]

        monkeypatch.setattr(health_router, "_READINESS_TIMEOUT_SECONDS", 0.05)
        health_router.set_broker_check(SlowBroker())
        slow = client.get("/v1/health/ready")
        assert slow.status_code == 503
        assert slow.json()["checks"]["broker"]["status"] == "not_ready"
    finally:
        health_router.set_broker_check(None)


def test_v1_health_ready_broker_health_check_probe() -> None:
    """A broker exposing health_check() drives readiness through the aggregator."""
    from app.api.v1.system.health_router import set_broker_check

    class HealthyBroker:
        async def health_check(self) -> dict[str, str]:
            return {"status": "up", "detail": "amqp"}

    class UnhealthyBroker:
        async def health_check(self) -> dict[str, str]:
            return {"status": "down", "detail": "no channel"}

    try:
        set_broker_check(HealthyBroker())
        healthy = client.get("/v1/health/ready")
        assert healthy.status_code == 200
        assert healthy.json()["checks"]["broker"]["status"] == "ready"
        assert healthy.json()["checks"]["broker"]["detail"] == "amqp"

        set_broker_check(UnhealthyBroker())
        unhealthy = client.get("/v1/health/ready")
        assert unhealthy.status_code == 503
        assert unhealthy.json()["checks"]["broker"]["status"] == "not_ready"
    finally:
        set_broker_check(None)


# ---------------------------------------------------------------------------
# B4-bis Constat 3 — the health endpoints must not lie about the real state
# ---------------------------------------------------------------------------


def test_health_reports_llm_not_configured(monkeypatch: Any) -> None:
    """Without LLM_API_KEY the LLM check is not_configured, never ready."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    res = client.get("/v1/health")

    assert res.status_code == 200
    llm = res.json()["checks"]["llm"]
    assert llm["status"] == "not_configured"
    assert llm["configured"] is False
    assert "LLM_API_KEY" in llm["reason"]


def test_health_reports_database_not_configured_without_url(monkeypatch: Any) -> None:
    """Without INIS_DATABASE_URL the database check is not_configured."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

    res = client.get("/v1/health")

    database = res.json()["checks"]["database"]
    assert database["status"] == "not_configured"
    assert database["configured"] is False


def test_health_reports_broker_not_configured_without_url(monkeypatch: Any) -> None:
    """Without AMQP_URL/INIS_BROKER_URL the broker check is not_configured."""
    monkeypatch.delenv("AMQP_URL", raising=False)
    monkeypatch.delenv("INIS_BROKER_URL", raising=False)

    res = client.get("/v1/health")

    broker = res.json()["checks"]["broker"]
    assert broker["status"] == "not_configured"
    assert broker["configured"] is False


def test_health_ready_degraded_when_llm_stub(monkeypatch: Any) -> None:
    """The pipeline depends on the LLM, so a stub-only LLM means degraded."""
    # Hermetic via _hermetic_health_env (no LLM_API_KEY): LLM check reports
    # not_configured -> global degraded (200), never not_ready (503).
    res = client.get("/v1/health/ready")

    assert res.status_code == 200
    assert res.json()["status"] == "degraded"
    assert res.json()["checks"]["llm"]["status"] == "not_configured"


def test_health_exposes_the_full_contract() -> None:
    """/v1/health exposes {status, version, circuit_breakers, checks{...}} (§32)."""
    res = client.get("/v1/health")

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"status", "version", "circuit_breakers", "checks", "migrations", "build"}
    assert "head" in body["migrations"]
    assert "git_sha" in body["build"]
    assert set(body["checks"]) == {"database", "redis", "broker", "llm"}
    assert body["version"] == "2.0.0"
    assert isinstance(body["circuit_breakers"], dict)


def test_health_llm_down_when_configured_but_unreachable(monkeypatch: Any) -> None:
    """A configured LLM that cannot be reached is reported as not_ready."""
    monkeypatch.setenv("LLM_API_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")

    res = client.get("/v1/health/ready")

    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"
    assert res.json()["checks"]["llm"]["status"] == "not_ready"


