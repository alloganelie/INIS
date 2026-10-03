"""Integration tests for the Â§41.14 migration contract.

The session-wide database is already at ``head`` (``tests/conftest.py``), so
this module does not touch it: a scratch database is created inside the same
container, migrated, rolled back to ``base`` and migrated again. That proves
the two properties a release needs â€” ``upgrade`` builds the full Â§27 schema and
``downgrade`` really removes it (no half-migrated state).
"""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.containers import run_alembic_upgrade

SCRATCH_DB = "inis_migration_scratch"

#: A subset of Â§27 tables that must exist after ``upgrade head``.
SAMPLE_TABLES = ("agents", "information_units", "audit_events", "accounts", "embeddings")


def _with_database_url(db_url: str, database: str) -> str:
    """Return *db_url* pointed at another database of the same server."""
    return db_url.rsplit("/", 1)[0] + "/" + database


async def _run_sql(db_url: str, statement: str, *, autocommit: bool = False) -> None:
    """Execute one administrative statement outside a transaction."""
    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT" if autocommit else None)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _tables(db_url: str) -> set[str]:
    """Return the public table names of a database."""
    engine = create_async_engine(db_url)
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


def _alembic(arguments: list[str], database_url: str) -> None:
    """Run an alembic command against *database_url* (child process)."""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        ["python", "-m", "alembic", *arguments],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(arguments)} failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.fixture
async def scratch_database(db_url: str) -> str:
    """Create a throw-away database inside the pgvector container."""
    await _run_sql(db_url, f"DROP DATABASE IF EXISTS {SCRATCH_DB}", autocommit=True)
    await _run_sql(db_url, f"CREATE DATABASE {SCRATCH_DB}", autocommit=True)
    scratch_url = _with_database_url(db_url, SCRATCH_DB)
    try:
        yield scratch_url
    finally:
        await _run_sql(db_url, f"DROP DATABASE IF EXISTS {SCRATCH_DB}", autocommit=True)


class TestUpgrade:
    """Â§41.14 â€” ``upgrade head`` builds the schema on an empty database."""

    async def test_upgrade_creates_the_spec_tables(self, scratch_database: str) -> None:
        """The fresh database has no application table before the upgrade."""
        assert not (set(SAMPLE_TABLES) & await _tables(scratch_database))

        run_alembic_upgrade(scratch_database)

        tables = await _tables(scratch_database)
        missing = [name for name in SAMPLE_TABLES if name not in tables]
        assert not missing, f"missing after upgrade: {missing}"

    async def test_upgrade_is_idempotent(self, scratch_database: str) -> None:
        """Re-running ``upgrade head`` is a no-op, not an error."""
        run_alembic_upgrade(scratch_database)
        first = await _tables(scratch_database)
        run_alembic_upgrade(scratch_database)
        assert await _tables(scratch_database) == first

    async def test_heads_are_recorded(self, scratch_database: str) -> None:
        """``alembic_version`` pins exactly one head revision."""
        run_alembic_upgrade(scratch_database)
        await _run_sql(scratch_database, "SELECT 1")
        engine = create_async_engine(scratch_database)
        try:
            async with engine.connect() as conn:
                revisions = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars().all()
        finally:
            await engine.dispose()
        assert len(revisions) == 1

    async def test_pgvector_extension_is_available(self, scratch_database: str) -> None:
        """Migration 0001 installs the Â§16.1 extension on a fresh database."""
        run_alembic_upgrade(scratch_database)
        engine = create_async_engine(scratch_database)
        try:
            async with engine.connect() as conn:
                extensions = (
                    await conn.execute(text("SELECT extname FROM pg_extension"))
                ).scalars().all()
        finally:
            await engine.dispose()
        assert "vector" in extensions


class TestDowngrade:
    """Â§41.14 â€” a rollback must leave a coherent (empty) schema."""

    async def test_downgrade_base_removes_the_tables(self, scratch_database: str) -> None:
        """After ``downgrade base`` no application table is left behind."""
        run_alembic_upgrade(scratch_database)
        _alembic(["downgrade", "base"], scratch_database)
        remaining = set(SAMPLE_TABLES) & await _tables(scratch_database)
        assert not remaining, f"tables survived the rollback: {remaining}"

    async def test_rollback_then_upgrade_round_trips(self, scratch_database: str) -> None:
        """The full up/down/up cycle ends on the same schema."""
        run_alembic_upgrade(scratch_database)
        upgraded = await _tables(scratch_database)
        _alembic(["downgrade", "base"], scratch_database)
        run_alembic_upgrade(scratch_database)
        assert await _tables(scratch_database) == upgraded


class TestRevision0016:
    """§18.2 soft delete + §7 request payload, on a real PostgreSQL database."""

    async def test_upgrade_adds_the_columns_it_promises(self, scratch_database: str) -> None:
        """The content tables get ``deleted_at``, ``requests`` gets ``payload``."""
        run_alembic_upgrade(scratch_database)

        for table in SOFT_DELETE_TABLES:
            assert "deleted_at" in await _columns_of(scratch_database, table), table
        assert "payload" in await _columns_of(scratch_database, "requests")

    async def test_append_only_tables_are_left_alone(self, scratch_database: str) -> None:
        """Lineage, versions and audit keep their history (§12.1, §18.1, §20)."""
        run_alembic_upgrade(scratch_database)

        for table in APPEND_ONLY_TABLES:
            assert "deleted_at" not in await _columns_of(scratch_database, table), table

    async def test_partial_indexes_carry_the_not_deleted_predicate(
        self, scratch_database: str
    ) -> None:
        """The §18.2 read path (``deleted_at IS NULL``) is really indexed."""
        run_alembic_upgrade(scratch_database)

        for table in SOFT_DELETE_TABLES:
            definition = await _index_definition(scratch_database, f"ix_{table}_not_deleted")
            assert definition is not None, f"index partiel absent pour {table}"
            assert "deleted_at IS NULL" in definition

    async def test_downgrade_removes_exactly_what_the_upgrade_added(
        self, scratch_database: str
    ) -> None:
        """The reverse path is symmetric: no column and no index left behind."""
        run_alembic_upgrade(scratch_database)
        _alembic(["downgrade", "0015"], scratch_database)

        for table in SOFT_DELETE_TABLES:
            assert "deleted_at" not in await _columns_of(scratch_database, table), table
            assert await _index_definition(scratch_database, f"ix_{table}_not_deleted") is None
        assert "payload" not in await _columns_of(scratch_database, "requests")

    async def test_existing_rows_survive_the_upgrade(self, scratch_database: str) -> None:
        """Rows written before 0016 are still there after it, untouched."""
        _alembic(["upgrade", "0015"], scratch_database)
        await _seed_rows(scratch_database)

        run_alembic_upgrade(scratch_database)

        assert await _row_count(scratch_database, "sources") >= 1
        assert await _row_count(scratch_database, "requests") >= 1
        engine = create_async_engine(scratch_database)
        try:
            async with engine.connect() as conn:
                source = (
                    await conn.execute(
                        text("SELECT url, deleted_at FROM sources WHERE id = 'SRC_0016_SEED'")
                    )
                ).mappings().first()
                request = (
                    await conn.execute(
                        text(
                            "SELECT objective, payload FROM requests "
                            "WHERE request_id = 'REQ_0016_SEED'"
                        )
                    )
                ).mappings().first()
        finally:
            await engine.dispose()

        assert source is not None and source["url"] == "https://example.org/seed"
        assert source["deleted_at"] is None, "une ligne existante n'est pas supprimée par 0016"
        assert request is not None and request["objective"] == "données existantes"
        assert request["payload"] is None, "aucune payload inventée pour une ligne antérieure"

    async def test_rows_survive_a_downgrade_then_upgrade_cycle(
        self, scratch_database: str
    ) -> None:
        """A rollback of 0016 does not destroy the rows: only its own columns."""
        run_alembic_upgrade(scratch_database)
        await _seed_rows(scratch_database)

        _alembic(["downgrade", "0015"], scratch_database)
        assert await _row_count(scratch_database, "sources") >= 1
        assert await _row_count(scratch_database, "requests") >= 1

        run_alembic_upgrade(scratch_database)
        assert await _row_count(scratch_database, "sources") >= 1
        assert await _row_count(scratch_database, "requests") >= 1


#: §18.2 — the content tables revision 0016 gives a soft-delete column.
SOFT_DELETE_TABLES = (
    "sources",
    "documents",
    "datasets",
    "information_units",
    "evidence",
    "artifacts",
    "conflicts",
)

#: Append-only tables: lineage (§12.1), versions (§18.1) and audit (§20).
APPEND_ONLY_TABLES = ("transformations", "information_versions", "audit_events")


async def _columns_of(database_url: str, table: str) -> set[str]:
    """Return the column names of *table* (empty when the table is absent)."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :name"
                    ),
                    {"name": table},
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    return set(rows)


async def _index_definition(database_url: str, index: str) -> str | None:
    """Return the ``pg_indexes`` definition of *index*, or ``None``."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            return (
                await conn.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
                    {"name": index},
                )
            ).scalars().first()
    finally:
        await engine.dispose()


async def _seed_rows(database_url: str) -> None:
    """Insert one source and one request, before revision 0016 runs.

    They are the "existing data" the migration must not touch. The request
    carries no ``payload`` column yet: that is exactly what 0016 adds.
    """
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO sources (id, url, source_type, data_stage, created_at, updated_at) "
                    "VALUES ('SRC_0016_SEED', 'https://example.org/seed', 'web', 'raw', now(), now())"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO requests (request_id, request_type, objective, status) "
                    "VALUES ('REQ_0016_SEED', 'research', 'données existantes', 'received')"
                )
            )
    finally:
        await engine.dispose()


async def _row_count(database_url: str, table: str) -> int:
    """Return how many rows *table* holds."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            return (
                await conn.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            ).scalar_one()
    finally:
        await engine.dispose()

