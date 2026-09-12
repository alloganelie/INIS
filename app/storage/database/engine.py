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
