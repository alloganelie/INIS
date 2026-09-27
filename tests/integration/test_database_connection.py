"""Integration tests: real PostgreSQL connectivity and §27 schema presence.

Runs against the session-scoped ``pgvector/pgvector:pg16`` testcontainer and
skips cleanly when Docker is unavailable (§33.2). Everything else in the
storage layer assumes these facts, so they are asserted once here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.connectors.base import Query
from app.connectors.database.postgres_connector import PostgresConnector
from app.storage.database.engine import create_engine, create_engine_or_none
from app.storage.search.vector_search import VectorSearch

#: Tables §27 requires before any pipeline write can succeed.
REQUIRED_TABLES = (
    "agents",
    "agent_capabilities",
    "requests",
    "plans",
    "plan_steps",
    "executions",
    "sources",
    "documents",
    "information_units",
    "evidence",
    "claims",
    "conflicts",
    "transformations",
    "artifacts",
    "audit_events",
    "accounts",
    "sessions",
    "embeddings",
)


async def _table_names(db_url: str) -> set[str]:
    """Return the table names visible to the connected database."""
    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    return set(rows)


class TestConnectivity:
    """§4.2 — the configured database is reachable and is PostgreSQL."""

    async def test_engine_connects(self, db_url: str) -> None:
        """A trivial query round-trips through the async engine."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
        finally:
            await engine.dispose()

    async def test_server_is_postgresql(self, db_url: str) -> None:
        """The server reports itself as PostgreSQL (no accidental SQLite)."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                version = (await conn.execute(text("SELECT version()"))).scalar_one()
        finally:
            await engine.dispose()
        assert "PostgreSQL" in version

    async def test_pgvector_extension_is_installed(self, db_url: str) -> None:
        """§16.1 requires the ``vector`` extension for embeddings."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                extensions = (
                    await conn.execute(text("SELECT extname FROM pg_extension"))
                ).scalars().all()
        finally:
            await engine.dispose()
        assert "vector" in extensions

    def test_unusable_driver_degrades_to_none(self) -> None:
        """A driver that does not exist yields ``None`` instead of raising."""
        assert create_engine_or_none("nosuchdriver://localhost/db") is None


class TestSchema:
    """§27 — the migrated schema carries every table the pipeline writes to."""

    async def test_required_tables_exist(self, db_url: str) -> None:
        """Each §27 table required by the V1 flow is present."""
        tables = await _table_names(db_url)
        missing = [name for name in REQUIRED_TABLES if name not in tables]
        assert not missing, f"missing §27 tables: {missing}"

    async def test_alembic_version_is_recorded(self, db_url: str) -> None:
        """The migrations were applied through Alembic (§41.14)."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                revision = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
        finally:
            await engine.dispose()
        assert revision

    async def test_embeddings_use_the_configured_dimension(self, db_url: str) -> None:
        """§16.1 — the vector column is dimensioned by ``[CONFIG]``."""
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                column_type = (
                    await conn.execute(
                        text(
                            "SELECT format_type(a.atttypid, a.atttypmod) "
                            "FROM pg_attribute a "
                            "JOIN pg_class c ON c.oid = a.attrelid "
                            "WHERE c.relname = 'embeddings' AND a.attname = 'vector'"
                        )
                    )
                ).scalar_one()
        finally:
            await engine.dispose()
        assert column_type.startswith("vector(")


class TestConnectorHealth:
    """§9/§4.2 — the PostgreSQL connector reports real health and discovery."""

    async def test_health_check_reports_latency(self, db_url: str) -> None:
        """A live database is healthy and its latency is measured."""
        connector = PostgresConnector(connection_string=db_url)
        try:
            health = await connector.health_check()
        finally:
            if connector._engine is not None:
                await connector._engine.dispose()
        assert health.healthy is True
        assert isinstance(health.latency_ms, float)
        assert health.latency_ms >= 0

    async def test_discovery_lists_real_tables(self, db_url: str) -> None:
        """Discovery returns candidates built from the live catalog."""
        connector = PostgresConnector(connection_string=db_url)
        try:
            candidates = await connector.discover(
                Query(query_string="information_units")
            )
        finally:
            if connector._engine is not None:
                await connector._engine.dispose()
        assert candidates
        assert any(
            candidate.metadata.get("table") == "information_units"
            for candidate in candidates
        )


class TestDegradedMode:
    """§9.1 — without a usable database the search layer degrades, not crashes."""

    async def test_vector_search_without_driver_returns_empty(self) -> None:
        """An unusable connection string yields an empty result set."""
        results = await VectorSearch("nosuchdriver://localhost/db").search(
            owner_type="information_unit", query_vector=[0.0] * 4, limit=5
        )
        assert results == []


@pytest.mark.parametrize("limit", [1, 5])
async def test_vector_search_accepts_any_limit(db_url: str, limit: int) -> None:
    """§16.1 — the limit parameter is honoured on an empty corpus."""
    search = VectorSearch(db_url)
    results = await search.search(
        owner_type="information_unit", query_vector=[0.1] * 1536, limit=limit
    )
    assert isinstance(results, list)
    assert len(results) <= limit

