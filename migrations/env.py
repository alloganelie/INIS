"""Alembic environment configuration for INIS."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# The migration CLI is a first-class entry point for developers: it reads the
# same ``.env`` as the API (no-op in production, §19) so that
# ``docker compose up -d`` + ``make migrate`` work without exporting anything.
from app.core.env import bootstrap_environment

bootstrap_environment()

config = context.config
# ``INIS_DATABASE_URL`` is the canonical variable of the application (§4.2);
# ``DATABASE_URL`` remains accepted for tools that only know the generic name.
database_url = os.environ.get("INIS_DATABASE_URL") or os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    """Configure Alembic against a synchronous connection facade."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations through the SQLAlchemy async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online mode using the async Alembic pattern."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
