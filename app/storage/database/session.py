"""PostgreSQL async session factory for INIS storage layer.

``get_session`` is the canonical session provider; ``session_scope`` wraps it
in a context manager, and ``account_repository`` / ``session_repository`` hand
repositories a live session without letting callers double-close it.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine, AsyncSession

from app.storage.repositories.account_repository import AccountRepository
from app.storage.repositories.session_repository import SessionRepository

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


def database_configured() -> bool:
    """Return ``True`` when a PostgreSQL URL is configured for this process."""
    return bool(os.getenv("INIS_DATABASE_URL"))


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` bound to the configured engine.

    The session is closed by finishing the :func:`get_session` generator, which
    is the only correct way to release it: calling ``session.close()``
    separately double-closes the underlying transaction and makes SQLAlchemy
    raise ``IllegalStateChangeError``.

    Raises:
        RuntimeError: If no database is configured or the engine is unusable.
    """
    ensure_session_maker()
    generator = get_session()
    session = await anext(generator)
    try:
        yield session
    finally:
        await generator.aclose()


@asynccontextmanager
async def account_repository() -> AsyncIterator[AccountRepository]:
    """Yield an :class:`AccountRepository` bound to a live session.

    Used by the ``/v1/accounts`` and ``/v1/auth`` routers (B4-bis constat 2).
    """
    from app.storage.repositories.account_repository import AccountRepository as _Repo

    async with session_scope() as session:
        yield _Repo(session)


@asynccontextmanager
async def session_repository() -> AsyncIterator[SessionRepository]:
    """Yield a :class:`SessionRepository` bound to a live session."""
    async with session_scope() as session:
        yield SessionRepository(session)
