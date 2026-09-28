"""``store_source`` internal tool per §21.

Persists a :class:`~app.domain.entities.source.Source` in the ``sources`` table
and returns its identifier. The insert is idempotent on ``id``: storing the same
source twice updates ``updated_at`` instead of creating a duplicate (§18.1).

The SQL is the same shape the request pipeline already uses, so the tool and the
pipeline write one consistent row layout.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.source import Source
from app.tools.engine_access import resolve_engine

__all__ = ["store_source"]


def _json(payload: object) -> str:
    """Serialise a JSONB payload as text for the ``CAST(... AS JSONB)`` bind."""
    return json.dumps(payload, ensure_ascii=False, default=str)

_INSERT_SOURCE = text(
    """
    INSERT INTO sources (
        id, url, source_type, reliability_score, freshness,
        data_stage, created_at, updated_at
    ) VALUES (
        :id, :url, :source_type, :reliability_score, CAST(:freshness AS JSONB),
        :data_stage, :created_at, :updated_at
    )
    ON CONFLICT (id) DO UPDATE SET
        url = EXCLUDED.url,
        source_type = EXCLUDED.source_type,
        reliability_score = EXCLUDED.reliability_score,
        freshness = EXCLUDED.freshness,
        updated_at = EXCLUDED.updated_at
    """
)


async def store_source(
    source: Source,
    *,
    source_type: str | None = None,
    data_stage: str = "raw",
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
) -> str:
    """Store *source* and return its ``source_id`` (§21).

    Args:
        source: The source to persist. Its ``source_id`` is the primary key.
        source_type: Value of the ``source_type`` column; ``Source.type`` is
            used when omitted.
        data_stage: Value of the ``data_stage`` column (default ``raw``).
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        The stored ``source_id``.

    Raises:
        ValidationError: If the source has no usable ``source_id``.
        InfrastructureError: If no engine is available or the insert fails.
    """
    source_id = str(source.source_id or "").strip()
    if not source_id:
        raise ValidationError("source.source_id is required to store a source")

    active_engine = resolve_engine(engine, connection_string, component="store_source")
    now = datetime.now(UTC)
    parameters = {
        "id": source_id,
        "url": source.url,
        "source_type": source_type or str(source.type),
        "reliability_score": float(source.reliability_score),
        "freshness": _json(source.freshness or {}),
        "data_stage": data_stage,
        "created_at": now,
        "updated_at": now,
    }
    try:
        async with active_engine.begin() as connection:
            await connection.execute(_INSERT_SOURCE, parameters)
    except Exception as exc:
        raise InfrastructureError(f"store_source failed: {exc}") from exc
    return source_id
