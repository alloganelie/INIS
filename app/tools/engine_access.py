"""Resolve the PostgreSQL engine shared by the §16/§21 database-backed tools.

The §21 signatures take no engine. Rather than silently returning an empty
result when PostgreSQL is unreachable — which would look like "no match"
instead of "no database" (§0.2) — the tools resolve an engine here and raise
:class:`~app.core.errors.InfrastructureError` when none is available.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError
from app.storage.database.engine import create_engine_or_none

__all__ = ["resolve_engine"]


def resolve_engine(
    engine: AsyncEngine | None,
    connection_string: str | None,
    *,
    component: str,
) -> AsyncEngine:
    """Return an async engine, raising when none can be built.

    Args:
        engine: Pre-built engine, used as-is when supplied.
        connection_string: PostgreSQL URL used when *engine* is ``None``.
        component: Name of the caller, included in the error message.

    Returns:
        The usable async engine.

    Raises:
        InfrastructureError: If no engine was supplied and none could be built
            from *connection_string*.
    """
    if engine is not None:
        return engine
    if connection_string:
        built = create_engine_or_none(connection_string)
        if built is not None:
            return built
    raise InfrastructureError(
        f"{component} requires PostgreSQL: pass an engine or a usable connection string"
    )
