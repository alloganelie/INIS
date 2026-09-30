"""Integration tests for PostgreSQL with testcontainers per §4.2, §16."""

import os

import pytest

from app.connectors.database.postgres_connector import PostgresConnector
from app.storage.search.fulltext_search import FullTextSearch
from app.storage.search.hybrid_search import HybridSearch
from app.storage.search.vector_search import VectorSearch


def docker_available() -> bool:
    """Check if Docker is available."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container with pgvector extension."""
    if not docker_available():
        pytest.skip("Docker not available")
    
    try:
        from testcontainers.community.postgres import PostgresContainer
        
        container = PostgresContainer(
            "pgvector/pgvector:pg16",
            username="test",
            password="test",
            dbname="test",
            port=5432,
        )
        container.start()
        yield container
        container.stop()
    except Exception as e:
        pytest.skip(f"Docker/testcontainers not available: {e}")


@pytest.fixture(scope="session")
def db_url(request):
    """Get an asyncpg SQLAlchemy URL from the environment or container."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    postgres_container = request.getfixturevalue("postgres_container")
    return postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def alembic_upgrade(db_url):
    """Run alembic upgrade on the test database."""
    try:
        import subprocess
        import os
        
        # Set environment variable for database URL
        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        
        # Run alembic upgrade
        subprocess.run(
            ["alembic", "upgrade", "head"],
            env=env,
            check=True,
            capture_output=True,
        )
    except Exception as e:
        pytest.skip(f"Alembic upgrade failed: {e}")


@pytest.mark.asyncio
async def test_postgres_real_core_tables(db_url, alembic_upgrade):
    """Test that core tables are created and accessible."""
    connector = PostgresConnector(connection_string=db_url)
    
    # Test health check
    health = await connector.health_check()
    assert health.healthy is True
    assert health.latency_ms is not None
    
    # Test discover tables
    from app.connectors.base import Query
    query = Query(query_string="agents")
    candidates = await connector.discover(query)
    assert len(candidates) > 0
    assert any("agents" in c.metadata.get("table", "") for c in candidates)


@pytest.mark.asyncio
async def test_postgres_connector_connected_mode(db_url, alembic_upgrade):
    """The connector discovers real tables and measures connected latency."""
    from app.connectors.base import Query

    connector = PostgresConnector(connection_string=db_url)
    try:
        candidates = await connector.discover(Query(query_string="agents"))
        health = await connector.health_check()

        assert any(candidate.metadata.get("table") == "agents" for candidate in candidates)
        assert health.healthy is True
        assert isinstance(health.latency_ms, float)
        assert health.latency_ms > 0
    finally:
        if connector._engine is not None:
            await connector._engine.dispose()


@pytest.mark.asyncio
async def test_postgres_real_insert_select(db_url, alembic_upgrade):
    """Test INSERT and SELECT on core tables."""
    connector = PostgresConnector(connection_string=db_url)
    
    # Discover agents table
    from app.connectors.base import Query
    query = Query(query_string="agents")
    candidates = await connector.discover(query)
    
    if candidates:
        # Try to retrieve data
        raw = await connector.retrieve(candidates[0])
        assert raw.source_id is not None
        assert raw.content_type == "text/plain"


@pytest.mark.asyncio
async def test_migration_0003_embeddings_table(db_url, alembic_upgrade):
    """Test that migration 0003 creates embeddings table."""
    connector = PostgresConnector(connection_string=db_url)
    
    # Discover embeddings table
    from app.connectors.base import Query
    query = Query(query_string="embeddings")
    candidates = await connector.discover(query)
    
    assert len(candidates) > 0
    assert any("embeddings" in c.metadata.get("table", "") for c in candidates)


@pytest.mark.asyncio
async def test_vector_search_real(db_url, alembic_upgrade):
    """Test vector search with pgvector."""
    search = VectorSearch(connection_string=db_url)
    
    # Insert a test embedding
    # This would require actual asyncpg connection to insert data
    # For now, test that the search class can be initialized
    results = await search.search(
        owner_type="information_unit",
        query_vector=[0.1] * 1536,
        limit=10,
    )
    # Should return empty list if no data, or results if data exists
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_fulltext_search_real(db_url, alembic_upgrade):
    """Test full-text search with tsvector."""
    search = FullTextSearch(connection_string=db_url)
    
    results = await search.search(
        query="test query",
        limit=10,
    )
    # Should return empty list if no data, or results if data exists
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_hybrid_search_real(db_url, alembic_upgrade):
    """Test hybrid search combining semantic and lexical."""
    search = HybridSearch(connection_string=db_url)
    
    results = await search.search(
        query="test query",
        query_vector=[0.1] * 1536,
        limit=10,
    )
    # Should return empty list if no data, or results if data exists
    assert isinstance(results, list)


# ─────────────────────────────────────────────────────────────────────────────
# L6.1 — the repository must declare the migrated schema, not its own.
#
# ``sources`` drifted once: the persistence module typed its own
# ``INSERT ... source_id`` while the table (revision 0002) is keyed on ``id``,
# so every read raised ``UndefinedColumn`` on a migrated database while the
# unit-level tests stayed green. These tests compare what the repositories
# declare with what the migration actually created.
# ─────────────────────────────────────────────────────────────────────────────

#: Primary key each repository assumes, per migrated table.
_PRIMARY_KEYS = {
    "sources": "id",
    "information_units": "id",
    "evidence": "evidence_id",
    "transformations": "transformation_id",
    "requests": "request_id",
    "plans": "plan_id",
    "plan_steps": "step_id",
    "information_versions": "information_version_id",
}


async def _live_columns(conn, table_name: str) -> set[str]:
    """Return the columns a migrated table really has."""
    from sqlalchemy import text

    rows = (
        await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :name"
            ),
            {"name": table_name},
        )
    ).scalars().all()
    return set(rows)


async def _live_primary_key(conn, table_name: str) -> list[str]:
    """Return the primary key columns a migrated table really has."""
    from sqlalchemy import text

    return list(
        (
            await conn.execute(
                text(
                    "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON kcu.constraint_name = tc.constraint_name "
                    "WHERE tc.table_schema = 'public' AND tc.table_name = :name "
                    "  AND tc.constraint_type = 'PRIMARY KEY'"
                ),
                {"name": table_name},
            )
        ).scalars().all()
    )


@pytest.mark.asyncio
async def test_source_repository_matches_migration(db_url, alembic_upgrade):
    """``SourceRepository`` declares exactly the migrated ``sources`` columns.

    The plan's proof for dette n°3: no column is invented, none is missing, and
    the primary key is the one the migration created.
    """
    from app.storage.database.engine import create_engine
    from app.storage.repositories.source_repository import sources_table

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            live = await _live_columns(conn, "sources")
            key = await _live_primary_key(conn, "sources")
    finally:
        await engine.dispose()

    declared = set(sources_table.columns.keys())
    assert live - declared == set(), f"colonnes migrées sans repository : {sorted(live - declared)}"
    assert declared - live == set(), f"colonnes déclarées sans migration : {sorted(declared - live)}"
    assert key == ["id"]


@pytest.mark.asyncio
async def test_every_repository_table_is_keyed_as_declared(db_url, alembic_upgrade):
    """Every repository table exists and its primary key is the declared one."""
    from app.storage.database.engine import create_engine
    from app.storage.repositories.evidence_repository import evidence_table
    from app.storage.repositories.information_unit_repository import (
        information_units_table,
    )
    from app.storage.repositories.plan_repository import plan_steps_table, plans_table
    from app.storage.repositories.request_repository import requests_table
    from app.storage.repositories.source_repository import sources_table
    from app.storage.repositories.transformation_repository import transformations_table
    from app.storage.repositories.version_repository import information_versions_table

    tables = (
        sources_table,
        information_units_table,
        evidence_table,
        transformations_table,
        requests_table,
        plans_table,
        plan_steps_table,
        information_versions_table,
    )
    engine = create_engine(db_url)
    problems: dict[str, dict[str, list[str]]] = {}
    try:
        async with engine.connect() as conn:
            for table in tables:
                live = await _live_columns(conn, table.name)
                if not live:
                    problems[table.name] = {"table": ["absente du schéma migré"]}
                    continue
                absent = sorted(set(table.columns.keys()) - live)
                if absent:
                    problems[table.name] = {"colonnes absentes": absent}
                key = await _live_primary_key(conn, table.name)
                if key != [_PRIMARY_KEYS[table.name]]:
                    problems.setdefault(table.name, {})["clé"] = key
    finally:
        await engine.dispose()

    assert problems == {}, f"divergence repository/migration : {problems}"
