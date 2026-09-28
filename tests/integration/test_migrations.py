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

