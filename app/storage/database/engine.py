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


#: Process-wide engine built from ``INIS_DATABASE_URL`` (one per process).
_DEFAULT_ENGINE: AsyncEngine | None = None
_DEFAULT_URL: str | None = None


def get_default_engine() -> AsyncEngine | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` when unset.

    The URL is re-read on every call so an environment change (tests, admin
    tooling) is picked up without a process restart; the engine itself is
    cached per URL to avoid leaking connection pools.
    """
    global _DEFAULT_ENGINE, _DEFAULT_URL
    db_url = os.getenv("INIS_DATABASE_URL")
    if not db_url:
        return None
    if _DEFAULT_ENGINE is None or _DEFAULT_URL != db_url:
        _DEFAULT_ENGINE = create_engine(db_url)
        _DEFAULT_URL = db_url
    return _DEFAULT_ENGINE


def set_default_engine(engine: AsyncEngine | None) -> None:
    """Override (or clear) the process-wide engine, for tests and tooling."""
    global _DEFAULT_ENGINE, _DEFAULT_URL
    _DEFAULT_ENGINE = engine
    _DEFAULT_URL = None
