"""PostgreSQL async session factory for INIS storage layer."""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine, AsyncSession


_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def init_session_maker(engine: AsyncEngine) -> None:
    """Initialize the global session maker with the given engine.

    Args:
        engine: Async SQLAlchemy engine.
    """
    global _session_maker
    _session_maker = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


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
