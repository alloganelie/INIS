"""Evidence repository on the migrated schema (§14.2, §27, §32).

The table mirrors ``evidence`` (revision 0007) plus the §14.2 columns added by
revision 0011 (``claim_id``, ``transformation_id``, ``strength``,
``epistemic_status``, ``provenance``). ``quote`` holds the excerpt: it is the
raw material the evidence rests on, and it is what the API exposes as
``excerpt``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, Text, insert, select

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
)

__all__ = ["EvidenceRepository", "evidence_table"]

evidence_metadata = MetaData()

evidence_table = Table(
    "evidence",
    evidence_metadata,
    Column("evidence_id", String(64), primary_key=True),
    Column("information_id", String(64), nullable=True),
    Column("source_id", String(64), nullable=True),
    Column("document_id", String(64), nullable=True),
    Column("claim_id", String(64), nullable=True),
    Column("transformation_id", String(64), nullable=True),
    Column("quote", Text, nullable=True),
    Column("confidence", Float, nullable=True),
    Column("strength", Float, nullable=True),
    Column("epistemic_status", String(32), nullable=True),
    Column("provenance", JSON_TYPE, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
)


def to_evidence_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``evidence`` row onto the §14.2 API payload."""
    data = dict(row)
    strength = data.get("strength")
    if strength is None:
        strength = data.get("confidence")
    raw_confidence = data.get("confidence")
    return {
        "evidence_id": data.get("evidence_id"),
        "claim_id": data.get("claim_id"),
        "information_id": data.get("information_id"),
        "source_id": data.get("source_id"),
        "document_id": data.get("document_id"),
        "dataset_id": None,
        "transformation_id": data.get("transformation_id"),
        "excerpt": data.get("quote"),
        "strength": float(strength) if strength is not None else 1.0,
        "confidence": (
            {"score": float(raw_confidence)} if raw_confidence is not None else {}
        ),
        "provenance": as_dict(data.get("provenance")),
        "epistemic_status": data.get("epistemic_status") or "fact",
        "created_at": as_iso(data.get("created_at")),
    }


class EvidenceRepository(TableRepository):
    """Persistence of the §14.2 evidence records."""

    _metadata = evidence_metadata
    _table = evidence_table

    @classmethod
    async def get(cls, engine: Any, evidence_id: str) -> dict[str, Any] | None:
        """Return one evidence record by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(evidence_table).where(evidence_table.c.evidence_id == evidence_id)
            )
            row = result.mappings().first()
        return to_evidence_response(row) if row else None

    @classmethod
    async def list(
        cls,
        engine: Any,
        source_id: str | None = None,
        information_id: str | None = None,
        claim_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List evidence records with optional filters."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            query = (
                select(evidence_table)
                .order_by(evidence_table.c.created_at.desc())
                .limit(limit)
            )
            if source_id:
                query = query.where(evidence_table.c.source_id == source_id)
            if information_id:
                query = query.where(evidence_table.c.information_id == information_id)
            if claim_id:
                query = query.where(evidence_table.c.claim_id == claim_id)
            result = await conn.execute(query)
            return [to_evidence_response(row) for row in result.mappings().all()]

    @classmethod
    async def create(cls, engine: Any, data: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one evidence record and return its §14.2 representation."""
        await cls.ensure_table(engine)
        item = dict(data)
        evidence_id = str(item.get("evidence_id") or ULID.new("EVID_"))
        now = datetime.now(timezone.utc)
        conf = item.get("confidence")
        conf_score = None
        if isinstance(conf, (int, float)):
            conf_score = float(conf)
        elif isinstance(conf, dict):
            conf_score = conf.get("score")
        strength = item.get("strength")
        if strength is None:
            strength = conf_score

        row = {
            "evidence_id": evidence_id,
            "information_id": item.get("information_id"),
            "source_id": item.get("source_id"),
            "document_id": None,
            "claim_id": item.get("claim_id"),
            "transformation_id": item.get("transformation_id"),
            "quote": item.get("excerpt") or item.get("quote"),
            "confidence": float(conf_score) if conf_score is not None else None,
            "strength": float(strength) if strength is not None else None,
            "epistemic_status": item.get("epistemic_status") or "fact",
            "provenance": dict(item.get("provenance") or {}),
            "created_at": as_datetime(item.get("created_at"), now),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(evidence_table).values(**row))
        return to_evidence_response(row)


def get_database_engine() -> Any | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` (in-memory mode)."""
    return get_default_engine()

