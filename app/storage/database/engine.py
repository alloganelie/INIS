"""PostgreSQL async engine factory for INIS storage layer."""

from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine, AsyncEngine


def create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    """Create an async SQLAlchemy engine for PostgreSQL.

    Args:
        database_url: PostgreSQL connection URL with asyncpg driver.
        echo: If True, log all SQL statements (useful for debugging).

    Returns:
        Configured async engine with pool_pre_ping enabled.
    """
    return sa_create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def create_engine_or_none(database_url: str, echo: bool = False) -> AsyncEngine | None:
    """Create an engine, returning ``None`` when the driver cannot be built.

    Used by the storage components that must stay constructible without a
    live database (startup order, unit tests, degraded deployments). The
    failure reason is deliberately swallowed here: callers that need the
    error must use :func:`create_engine` directly, so a ``None`` engine is
    always an explicit "persistence unavailable" signal.

    Args:
        database_url: PostgreSQL connection URL with asyncpg driver.
        echo: If True, log all SQL statements (useful for debugging).

    Returns:
        The configured engine, or ``None`` if the URL/driver is unusable.
    """
    try:
        return create_engine(database_url, echo=echo)
    except Exception:
        return None

