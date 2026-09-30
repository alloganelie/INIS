"""Conflict repository on the migrated schema (§14.3, §27, §32).

The table mirrors ``conflicts`` (revision 0005: ``conflict_id``,
``information_a``, ``information_b``, ``difference_type``, ``severity``,
``resolution_status``, ``resolution_evidence``).
"""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, insert, select

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_dict,
)

__all__ = ["ConflictRepository", "conflicts_table"]

conflicts_metadata = MetaData()

conflicts_table = Table(
    "conflicts",
    conflicts_metadata,
    Column("conflict_id", String(64), primary_key=True),
    Column("information_a", Text, nullable=False),
    Column("information_b", Text, nullable=False),
    Column("difference_type", String(64), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("resolution_status", String(32), nullable=False),
    Column("resolution_evidence", JSON_TYPE, nullable=False),
    # Revision 0016 — §18.2: set when the record is soft-deleted; a read
    # filters on ``deleted_at IS NULL`` (partial index of the same name).
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


def to_conflict_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``conflicts`` row onto the §14.3 API payload."""
    data = dict(row)
    conflict_id = data.get("conflict_id")
    info_a = data.get("information_a")
    info_b = data.get("information_b")
    status_val = data.get("resolution_status") or "open"
    raw_ev = data.get("resolution_evidence")
    if isinstance(raw_ev, list):
        evidence_list = [str(x) for x in raw_ev]
    elif isinstance(raw_ev, dict):
        evidence_list = list(raw_ev.values())
    else:
        evidence_list = []

    info_ids: list[str] = []
    if info_a:
        info_ids.append(info_a)
    if info_b:
        info_ids.append(info_b)

    return {
        "conflict_id": conflict_id,
        "information_a": info_a,
        "information_b": info_b,
        "information_ids": info_ids,
        "claim_ids": [],
        "difference_type": data.get("difference_type") or "value",
        "severity": data.get("severity") or "medium",
        "status": status_val,
        "resolution_status": status_val,
        "description": None,
        "resolution_evidence": evidence_list,
        "detected_at": None,
    }


class ConflictRepository(TableRepository):
    """Persistence of the §14.3 contradiction records."""

    _metadata = conflicts_metadata
    _table = conflicts_table

    @classmethod
    async def get(cls, engine: Any, conflict_id: str) -> dict[str, Any] | None:
        """Return one conflict record by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(conflicts_table).where(conflicts_table.c.conflict_id == conflict_id)
            )
            row = result.mappings().first()
        return to_conflict_response(row) if row else None

    @classmethod
    async def list(
        cls,
        engine: Any,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List conflict records with optional status filter."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            query = select(conflicts_table).limit(limit)
            if status:
                target_status = status.lower()
                query = query.where(conflicts_table.c.resolution_status == target_status)
            result = await conn.execute(query)
            return [to_conflict_response(row) for row in result.mappings().all()]

    @classmethod
    async def create(cls, engine: Any, data: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one conflict record and return its §14.3 representation."""
        await cls.ensure_table(engine)
        item = dict(data)
        conflict_id = str(item.get("conflict_id") or ULID.new("CONFLICT_"))
        status_val = item.get("status") or item.get("resolution_status") or "open"
        evidence = item.get("resolution_evidence")
        if evidence is None:
            evidence = []
        elif not isinstance(evidence, list):
            evidence = [evidence]

        info_a = item.get("information_a")
        info_b = item.get("information_b")
        if not info_a and item.get("information_ids"):
            info_ids = item.get("information_ids")
            if len(info_ids) > 0:
                info_a = info_ids[0]
            if len(info_ids) > 1:
                info_b = info_ids[1]

        row = {
            "conflict_id": conflict_id,
            "information_a": str(info_a or "INF_UNKNOWN_A"),
            "information_b": str(info_b or "INF_UNKNOWN_B"),
            "difference_type": str(item.get("difference_type") or "value"),
            "severity": str(item.get("severity") or "medium"),
            "resolution_status": str(status_val),
            "resolution_evidence": list(evidence),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(conflicts_table).values(**row))
        return to_conflict_response(row)


def get_database_engine() -> Any | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` (in-memory mode)."""
    return get_default_engine()
