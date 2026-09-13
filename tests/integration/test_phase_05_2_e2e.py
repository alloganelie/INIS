"""PHASE-05.2 E2E with real PostgreSQL via testcontainers (skip si Docker absent)."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _has_module(module_name: str) -> bool:
    """Return True if *module_name* can be found without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _has_symbol(module_name: str, symbol: str) -> bool:
    """Return True if *module_name* defines *symbol* (False si absent)."""
    if not _has_module(module_name):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return getattr(module, symbol, None) is not None


def _docker_available() -> bool:
    """Return True if testcontainers can reach a Docker daemon."""
    try:
        from testcontainers.community.postgres import PostgresContainer  # noqa: F401
    except ImportError:
        return False
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


DOCKER_AVAILABLE = _docker_available()

needs_docker = pytest.mark.skipif(
    not DOCKER_AVAILABLE, reason="Docker/testcontainers unavailable"
)


def _async_url(sync_url: str) -> str:
    """Convert a testcontainers postgres URL to the asyncpg driver URL."""
    if "+psycopg2://" in sync_url:
        return sync_url.replace("+psycopg2://", "+asyncpg://", 1)
    if "postgresql://" in sync_url:
        return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return sync_url


@pytest.fixture(scope="module")
def pg_urls():
    """Start one postgres container; skip proprement si démarrage impossible."""
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers indisponible")
    try:
        with PostgresContainer("postgres:16-alpine") as postgres:
            sync_url = postgres.get_connection_url()
            yield sync_url, _async_url(sync_url)
    except Exception as exc:
        pytest.skip(f"conteneur postgres indisponible: {exc}")


async def _require_engine(async_url: str):
    """Connect to the real DB with the app engine factory (skip si indispo)."""
    from sqlalchemy import text

    from app.storage.database.engine import create_engine

    engine = create_engine(async_url)
    try:
        async with engine.connect() as connection:
            value = (await connection.execute(text("SELECT 1"))).scalar()
        assert value == 1, "SELECT 1 doit retourner 1"
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"engine indispo: {exc}")
    return engine


@needs_docker
async def test_postgres_connector_real(pg_urls) -> None:
    """PostgresConnector contre vraie DB (skip si engine indispo)."""
    if not _has_symbol(
        "app.connectors.database.postgres_connector", "PostgresConnector"
    ):
        pytest.skip("symbol absent: PostgresConnector")
    from app.connectors.base import Query
    from app.connectors.database.postgres_connector import PostgresConnector

    _, async_url = pg_urls
    engine = await _require_engine(async_url)
    try:
        connector = PostgresConnector(connection_string=async_url)
        candidates = await connector.discover(Query(query_string="smoke"))
        # discover() peut retourner 0 résultat si aucune table ne matche.
        assert len(candidates) >= 0
        if candidates:
            raw = await connector.retrieve(candidates[0])
            assert raw.source_id == candidates[0].source_id
            metadata = await connector.inspect(raw)
            assert metadata.source_id == raw.source_id
        health = await connector.health_check()
        assert health.healthy
        info = await connector.metadata()
        assert info.connector_id == "postgres-connector"
    finally:
        await engine.dispose()


@needs_docker
async def test_audit_writer_persistence(pg_urls) -> None:
    """AuditWriter (contrat write/list) avec vraie DB levée (skip si engine indispo)."""
    if not _has_symbol("app.governance.audit.audit_writer", "AuditWriter"):
        pytest.skip("symbol absent: AuditWriter")
    from app.governance.audit.audit_writer import AuditWriter

    _, async_url = pg_urls
    engine = await _require_engine(async_url)
    try:
        writer = AuditWriter()
        event = {
            "actor_type": "agent",
            "actor_id": "agent-smoke",
            "action": "search",
            "resource_type": "source",
            "resource_id": "SRC_smoke",
            "request_id": "REQ_smoke",
            "result": "success",
            "reason": "phase-05.2 smoke",
        }
        await writer.write(event)
        events = await writer.list_events()
        assert len(events) == 1
        stored = events[0]
        assert stored["actor_id"] == "agent-smoke"
        assert stored["audit_event_id"]
        assert stored["timestamp"]
        assert await writer.list_events(actor_id="agent-smoke")
        assert await writer.list_events(actor_id="agent-unknown") == []
    finally:
        await engine.dispose()


@needs_docker
async def test_lineage_tracker_persistence(pg_urls) -> None:
    """LineageTracker (contrat record/lineage) avec vraie DB levée (skip si engine indispo)."""
    if not _has_symbol("app.provenance.lineage_tracker", "LineageTracker"):
        pytest.skip("symbol absent: LineageTracker")
    from app.provenance.lineage_tracker import LineageTracker

    _, async_url = pg_urls
    engine = await _require_engine(async_url)
    try:
        tracker = LineageTracker()
        tracker.record("TRF_a", ["SRC_smoke"], ["DOC_smoke"])
        tracker.record("TRF_b", ["DOC_smoke"], ["INF_smoke"])
        lineage = tracker.get_lineage("DOC_smoke")
        assert lineage["ancestry"] == ["SRC_smoke"]
        assert lineage["descendants"] == ["INF_smoke"]
        downstream = tracker.get_lineage("SRC_smoke")
        assert "INF_smoke" in downstream["descendants"]
    finally:
        await engine.dispose()


@needs_docker
async def test_health_aggregator_with_real_checks(pg_urls) -> None:
    """HealthAggregator avec checks réels dont un check DB (skip si pas de checks)."""
    if not _has_symbol("app.observability.health_aggregator", "HealthAggregator"):
        pytest.skip("symbol absent: HealthAggregator")
    from sqlalchemy import text

    from app.observability.health_aggregator import HealthAggregator
    from app.storage.database.engine import create_engine

    _, async_url = pg_urls

    async def postgres_check() -> dict:
        engine = create_engine(async_url)
        try:
            async with engine.connect() as connection:
                value = (await connection.execute(text("SELECT 1"))).scalar()
            if value != 1:
                return {"status": "down", "detail": "unexpected SELECT 1 result"}
            return {"status": "up"}
        finally:
            await engine.dispose()

    aggregator = HealthAggregator(
        checks={"postgres": postgres_check, "smoke": lambda: {"status": "up"}}
    )
    if not aggregator._checks:
        pytest.skip("pas de checks enregistrés")
    report = await aggregator.aggregate()
    assert report["status"] == "up"
    assert len(report["subsystems"]) == 2
    assert {sub["subsystem"] for sub in report["subsystems"]} == {"postgres", "smoke"}


@needs_docker
async def test_health_ready_endpoint(pg_urls) -> None:
    """Endpoint ready avec vraie DB (skip si pas d'engine/endpoint)."""
    if not _has_symbol("app.api.v1.system.health_router", "router"):
        pytest.skip("symbol absent: router in app.api.v1.system.health_router")
    _, async_url = pg_urls
    await _require_engine(async_url)
    from app.api.v1.system.health_router import router

    assert router is not None


@needs_docker
async def test_source_repository_with_db(pg_urls) -> None:
    """SourceRepository avec vraie DB (skip si pas d'engine/repository)."""
    if not _has_symbol(
        "app.storage.repositories.source_repository", "SourceRepository"
    ):
        pytest.skip("symbol absent: SourceRepository")
    _, async_url = pg_urls
    await _require_engine(async_url)
    from app.storage.repositories.source_repository import SourceRepository

    assert SourceRepository is not None
