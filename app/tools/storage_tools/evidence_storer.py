"""``store_evidence`` internal tool per §21.

Persists a §14 :class:`~app.domain.entities.evidence.Evidence` entry and returns
its identifier. Evidence is what allows a factual statement to be traced back to
a source excerpt, so a missing ``source_id`` is refused here rather than stored
as an untraceable row (§0.2, §33.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.evidence import Evidence
from app.tools.engine_access import resolve_engine

__all__ = ["store_evidence"]

_INSERT_EVIDENCE = text(
    """
    INSERT INTO evidence (evidence_id, information_id, source_id, document_id, quote, confidence, created_at)
    VALUES (:evidence_id, :information_id, :source_id, :document_id, :quote, :confidence, :created_at)
    ON CONFLICT (evidence_id) DO UPDATE SET
        quote = EXCLUDED.quote,
        confidence = EXCLUDED.confidence
    """
)


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


async def store_evidence(
    evidence: Evidence | Mapping[str, Any],
    *,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
) -> str:
    """Store an evidence entry and return its ``evidence_id`` (§21).

    Args:
        evidence: The §14 entity, or an equivalent mapping carrying
            ``evidence_id``, ``source_id`` and an excerpt.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        The stored ``evidence_id``.

    Raises:
        ValidationError: If the evidence carries no ``evidence_id``, no
            ``source_id``, or no excerpt to quote.
        InfrastructureError: If no engine is available or the insert fails.
    """
    payload = _as_mapping(evidence)
    evidence_id = str(payload.get("evidence_id") or "").strip()
    if not evidence_id:
        raise ValidationError("evidence requires an evidence_id")
    source_id = str(payload.get("source_id") or "").strip()
    if not source_id:
        raise ValidationError(f"evidence {evidence_id} requires a source_id (§0.2)")
    quote = payload.get("quote") or payload.get("excerpt")
    if not quote or not str(quote).strip():
        raise ValidationError(
            f"evidence {evidence_id} requires a non-empty excerpt (§14.1)"
        )

    strength = payload.get("strength")
    active_engine = resolve_engine(engine, connection_string, component="store_evidence")
    parameters = {
        "evidence_id": evidence_id,
        "information_id": payload.get("information_id"),
        "source_id": source_id,
        "document_id": payload.get("document_id") or None,
        "quote": str(quote),
        "confidence": float(strength) if strength is not None else None,
        "created_at": datetime.now(UTC),
    }
    try:
        async with active_engine.begin() as connection:
            await connection.execute(_INSERT_EVIDENCE, parameters)
    except Exception as exc:
        raise InfrastructureError(f"store_evidence failed: {exc}") from exc
    return evidence_id
