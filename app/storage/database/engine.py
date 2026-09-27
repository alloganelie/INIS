"""PostgreSQL async engine factory for INIS storage layer."""

import os
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine, AsyncEngine
from sqlalchemy.pool import NullPool


def create_engine(database_url: str, echo: bool = False, poolclass: type | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine for PostgreSQL.

    Args:
        database_url: PostgreSQL connection URL with asyncpg driver.
        echo: If True, log all SQL statements (useful for debugging).
        poolclass: Optional connection pool class. Uses NullPool when testing
            across short-lived event loops to prevent asyncpg connection leakage.

    Returns:
        Configured async engine with pool_pre_ping enabled.
    """
    kwargs: dict = {"echo": echo}
    effective_pool = poolclass
    if effective_pool is None and os.getenv("INIS_NULL_POOL", "").lower() in ("1", "true", "yes"):
        effective_pool = NullPool
    if effective_pool is not None:
        kwargs["poolclass"] = effective_pool
    else:
        kwargs["pool_pre_ping"] = True
    return sa_create_async_engine(database_url, **kwargs)


def create_engine_or_none(database_url: str, echo: bool = False) -> AsyncEngine | None:
    """Create an engine, returning None when the driver cannot be built."""
    try:
        return create_engine(database_url, echo=echo)
    except Exception:
        return None
