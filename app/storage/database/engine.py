"""PostgreSQL async engine factory for INIS storage layer."""

import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine
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
#: Boucle d'événements qui a construit l'engine caché. Un pool asyncpg est lié à
#: sa boucle : le réutiliser depuis une autre lève ``RuntimeError: Event loop is
#: closed`` (piège P14 du plan de conformité). On mémorise donc la boucle, pas
#: seulement l'URL.
_DEFAULT_LOOP: asyncio.AbstractEventLoop | None = None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    """Return the loop currently running, or ``None`` outside any loop."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def get_default_engine() -> AsyncEngine | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` when unset.

    The URL is re-read on every call so an environment change (tests, admin
    tooling) is picked up without a process restart; the engine itself is cached
    per ``(URL, boucle)``. Un moteur — donc son pool — appartient à la boucle qui
    l'a créé : le recréer dès que la boucle change est ce qui évite le piège P14
    (« ``RuntimeError: Event loop is closed`` » quand deux tests ``pytest-asyncio``,
    ou un test synchrone puis ``asyncio.run(...)``, réutilisent le même pool).
    Recréer l'engine au changement de boucle est le comportement prescrit par le
    plan : « créer l'engine dans la boucle qui l'utilise ».

    ⚠️ L'ancien moteur est abandonné sans ``dispose()`` : ses connexions
    appartiennent à une boucle fermée, et les fermer depuis la nouvelle boucle
    lèverait précisément l'erreur qu'on veut éviter. ``INIS_NULL_POOL=1`` reste
    disponible pour des boucles très courtes, où l'on préfère ne rien garder.
    """
    global _DEFAULT_ENGINE, _DEFAULT_URL, _DEFAULT_LOOP
    db_url = os.getenv("INIS_DATABASE_URL")
    if not db_url:
        return None
    loop = _running_loop()
    if _DEFAULT_ENGINE is None or _DEFAULT_URL != db_url or _DEFAULT_LOOP is not loop:
        _DEFAULT_ENGINE = create_engine(db_url)
        _DEFAULT_URL = db_url
        _DEFAULT_LOOP = loop
    return _DEFAULT_ENGINE


def set_default_engine(engine: AsyncEngine | None) -> None:
    """Override (or clear) the process-wide engine, for tests and tooling."""
    global _DEFAULT_ENGINE, _DEFAULT_URL, _DEFAULT_LOOP
    _DEFAULT_ENGINE = engine
    _DEFAULT_URL = None
    _DEFAULT_LOOP = None
