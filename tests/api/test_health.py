"""Tests for health and version endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_version_returns_version() -> None:
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.1.0"
    assert "commit" in data
    assert isinstance(data["commit"], str)
    assert len(data["commit"]) > 0


def test_v1_health_ready_default() -> None:
    """Ensure GET /v1/health/ready returns 200 with ready status by default."""
    res = client.get("/v1/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] == "ready"
    assert "broker" in data["checks"]
    assert data["checks"]["broker"]["status"] == "ready"


def test_v1_health_ready_with_database(monkeypatch: any) -> None:
    """Ensure GET /v1/health/ready executes SELECT 1 when INIS_DATABASE_URL is set."""
    monkeypatch.setenv("INIS_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    res = client.get("/v1/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["status"] == "ready"


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

        # 2. Connected broker -> 200
        set_broker_check(DummyBroker(connected=True))
        res_ok = client.get("/v1/health/ready")
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "ready"
        assert res_ok.json()["checks"]["broker"]["status"] == "ready"
    finally:
        set_broker_check(None)


def test_v1_health_exposes_circuit_breaker_states() -> None:
    """§41.8: /v1/health must expose open | closed | half_open per scope."""
    from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
    from app.connectors.resilience.circuit_breaker import registry

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
        assert res.json()["status"] == "ready"
    finally:
        registry.reset(default_config=CircuitBreakerConfig())


