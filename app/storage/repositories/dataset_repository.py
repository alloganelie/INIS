"""Persistence of the ingested datasets (§11, §18.1, §27).

The table is the one revision ``0007`` created, plus the columns revision ``0015``
adds: ``storage_ref`` (where the rows came from — the §27 ``Dataset`` entity
carries it) and ``request_id`` (which request the ingestion was done for).

``name`` is NOT NULL in the schema: it holds the name of the file the rows were
read from, which is what a human looks for — never an invented label.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    update,
)

from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
)

__all__ = ["DatasetRepository", "datasets_table"]

datasets_metadata = MetaData()

datasets_table = Table(
    "datasets",
    datasets_metadata,
    Column("dataset_id", String(64), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("source_id", String(64), nullable=True),
    Column("row_count", Integer, nullable=True),
    Column("schema", JSON_TYPE, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    # Revision 0015 — what the ingestion needs to stay traceable.
    Column("storage_ref", Text, nullable=True),
    Column("request_id", String(64), nullable=True),
    # Revision 0016 — §18.2: set when the record is soft-deleted; a read
    # filters on ``deleted_at IS NULL`` (partial index of the same name).
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


def to_dataset_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``datasets`` row onto the §11/§27 payload."""
    data = dict(row)
    return {
        "dataset_id": data.get("dataset_id"),
        "name": data.get("name"),
        "source_id": data.get("source_id"),
        "request_id": data.get("request_id"),
        "row_count": data.get("row_count"),
        "dataset_schema": as_dict(data.get("schema")),
        "storage_ref": data.get("storage_ref"),
        "created_at": as_iso(data.get("created_at")),
        # Décision ``0016`` (§18.2) : la date de retrait fait partie de ce qu'une
        # lecture doit dire — sans elle, un lecteur ne peut pas distinguer
        # « retiré » de « jamais présent », et une requête §18.2 n'a rien à
        # filtrer. Même projection que l'artefact.
        "deleted_at": as_iso(data.get("deleted_at")),
    }


class DatasetRepository(TableRepository):
    """Persistence of the §11 datasets."""

    _metadata = datasets_metadata
    _table = datasets_table

    @classmethod
    async def get(cls, engine: Any, dataset_id: str) -> dict[str, Any] | None:
        """Return one dataset by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(datasets_table).where(datasets_table.c.dataset_id == dataset_id)
            )
            row = result.mappings().first()
        return to_dataset_response(row) if row else None

    @classmethod
    async def list_for_request(
        cls,
        engine: Any,
        request_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return the datasets ingested for *request_id*, newest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(datasets_table)
                .where(datasets_table.c.request_id == request_id)
                .order_by(datasets_table.c.created_at.desc(), datasets_table.c.dataset_id.desc())
                .limit(limit)
            )
            rows = result.mappings().all()
        return [to_dataset_response(row) for row in rows]

    @classmethod
    async def create(cls, engine: Any, record: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one dataset and return its stored representation.

        Idempotent on ``dataset_id``: re-ingesting the same document returns the
        row already stored instead of raising (CODING_RULES §1.10).
        """
        await cls.ensure_table(engine)
        dataset_id = str(record.get("dataset_id") or "")
        if not dataset_id:
            raise ValueError("dataset_id is required to persist a dataset (§11)")
        existing = await cls.get(engine, dataset_id)
        if existing is not None:
            return existing

        row_count = record.get("row_count")
        row: dict[str, Any] = {
            "dataset_id": dataset_id,
            # §27 — ``name`` is NOT NULL; the file name is the honest label.
            "name": str(record.get("name") or dataset_id)[:200],
            "source_id": record.get("source_id"),
            "row_count": int(row_count) if row_count is not None else None,
            "schema": dict(record.get("dataset_schema") or {}),
            "created_at": as_datetime(record.get("created_at"), datetime.now(UTC)),
            "storage_ref": record.get("storage_ref"),
            "request_id": record.get("request_id"),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(datasets_table).values(**row))
        return to_dataset_response(row)

    @classmethod
    async def soft_delete(cls, engine: Any, dataset_id: str) -> dict[str, Any] | None:
        """Remove one dataset from the active set (§18.2, décision ``0016``).

        Aucune suppression physique : seul ``deleted_at`` est renseigné (la table
        n'a pas de colonne de statut), et la ligne reste lisible pour expliquer
        ce qui a été livré et pourquoi il ne l'est plus.

        Args:
            engine: moteur de base de données.
            dataset_id: le jeu de données à retirer de l'ensemble actif.

        Returns:
            Le dataset relu (marqué), ou ``None`` s'il n'existe pas.
        """
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                update(datasets_table)
                .where(
                    datasets_table.c.dataset_id == dataset_id,
                    datasets_table.c.deleted_at.is_(None),
                )
                .values(deleted_at=datetime.now(UTC))
            )
            if not result.rowcount:
                return None
        return await cls.get(engine, dataset_id)
