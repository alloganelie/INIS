"""``store_information`` internal tool per §21.

Persists a §11 :class:`~app.domain.entities.information_unit.InformationUnit` and
returns its identifier, which is what makes a finding traceable later (§33.4).
The insert is idempotent on ``id``, so re-running a step that already wrote its
units cannot duplicate them.

The ``information_units`` table declares a foreign key on ``sources.id``: a unit
whose source was never stored is refused by PostgreSQL and that refusal is
surfaced as :class:`~app.core.errors.InfrastructureError` instead of being
hidden. Store the source first with ``store_source``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.information_unit import InformationUnit
from app.tools.engine_access import resolve_engine

__all__ = ["store_information"]

_INSERT_UNIT = text(
    """
    INSERT INTO information_units (id, type, content, source_id, document_id, data_stage, created_at)
    VALUES (:id, :type, CAST(:content AS JSONB), :source_id, :document_id, :data_stage, :created_at)
    ON CONFLICT (id) DO UPDATE SET
        type = EXCLUDED.type,
        content = EXCLUDED.content,
        data_stage = EXCLUDED.data_stage
    """
)


def _json(payload: object) -> str:
    """Serialise a JSONB payload as text for the ``CAST(... AS JSONB)`` bind."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def _as_mapping(value: Any) -> dict:
    """Return a mapping for *value*, tolerating pydantic models."""
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


async def store_information(
    unit: InformationUnit | Mapping[str, Any],
    *,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
) -> str:
    """Store an information unit and return its ``information_id`` (§21).

    Args:
        unit: The §11 entity, or an equivalent mapping carrying
            ``information_id`` (or ``id``) and ``source_id``.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        The stored ``information_id``.

    Raises:
        ValidationError: If the unit carries no identifier or no ``source_id``.
        InfrastructureError: If no engine is available or the insert fails
            (including the ``sources`` foreign-key violation).
    """
    payload = _as_mapping(unit)
    information_id = str(payload.get("information_id") or payload.get("id") or "").strip()
    if not information_id:
        raise ValidationError("information unit requires an information_id")
    source_id = str(payload.get("source_id") or "").strip()
    if not source_id:
        raise ValidationError(
            f"information unit {information_id} requires a source_id (§0.2)"
        )

    active_engine = resolve_engine(
        engine, connection_string, component="store_information"
    )
    parameters = {
        "id": information_id,
        "type": str(payload.get("type") or "text"),
        "content": _json(payload.get("content") or {}),
        "source_id": source_id,
        "document_id": payload.get("document_id") or None,
        "data_stage": str(payload.get("data_stage") or "raw"),
        "created_at": datetime.now(UTC),
    }
    try:
        async with active_engine.begin() as connection:
            await connection.execute(_INSERT_UNIT, parameters)
    except Exception as exc:
        raise InfrastructureError(f"store_information failed: {exc}") from exc
    return information_id
