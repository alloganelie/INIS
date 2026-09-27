"""PostgreSQL async session factory for INIS storage layer."""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine, AsyncSession


_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
_session_engine: Optional[AsyncEngine] = None


def init_session_maker(engine: AsyncEngine) -> None:
    """Initialize the global session maker with the given engine.

    Args:
        engine: Async SQLAlchemy engine.
    """
    global _session_maker, _session_engine
    _session_engine = engine
    _session_maker = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


def reset_session_maker() -> None:
    """Clear the global session maker (primarily for test isolation)."""
    global _session_maker, _session_engine
    _session_maker = None
    _session_engine = None


def ensure_session_maker(engine: Optional[AsyncEngine] = None) -> bool:
    """Initialize the session maker from *engine* or ``INIS_DATABASE_URL``.

    Returns ``True`` when the session maker is ready to vend sessions, or
    ``False`` when no database is configured / constructible.
    """
    global _session_maker, _session_engine
    if engine is not None:
        if _session_maker is None or _session_engine is not engine:
            init_session_maker(engine)
        return True

    import os
    from app.storage.database.engine import create_engine_or_none

    db_url = os.getenv("INIS_DATABASE_URL")
    if not db_url:
        return False
    built = create_engine_or_none(db_url)
    if built is None:
        return False
    if _session_maker is None or _session_engine is None:
        init_session_maker(built)
    return True


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-style session provider for FastAPI or other frameworks.

    Yields:
        AsyncSession instance that is automatically closed after use.

    Raises:
        RuntimeError: If session maker has not been initialized.
    """
    if _session_maker is None:
        raise RuntimeError("Session maker not initialized. Call init_session_maker first.")

    async with _session_maker() as session:
        yield session
