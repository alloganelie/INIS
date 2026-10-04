"""Information Unit repository on the migrated schema (§11, §27, §32).

The table mirrors ``information_units`` (revision 0002) plus the §11 columns
added by revision 0011 (``raw_reference``, ``context``, ``language``,
``epistemic_status``, ``provenance``, ``updated_at``). ``search_vector`` is
intentionally absent from this definition: it is a PostgreSQL-only
``tsvector`` maintained by the revision 0012 trigger, never written by the
application (which would fight the trigger).

Before this repository existed, ``GET /v1/information/{id}`` only read a
process-local dict the pipeline never filled, so every persisted unit answered
404 while its row was sitting in PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select, update

from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine
from app.storage.repositories.document_repository import documents_table
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
)

__all__ = ["InformationUnitRepository", "information_units_table"]

information_units_metadata = MetaData()

information_units_table = Table(
    "information_units",
    information_units_metadata,
    Column("id", String(64), primary_key=True),
    Column("type", String(32), nullable=False),
    Column("content", JSON_TYPE, nullable=False),
    Column("source_id", String(64), nullable=False),
    Column("document_id", String(64), nullable=True),
    # Revision 0015 — §11: which dataset the unit belongs to, and where it is.
    Column("dataset_id", String(64), nullable=True),
    Column("location", JSON_TYPE, nullable=True),
    Column("data_stage", String(32), nullable=False),
    Column("raw_reference", JSON_TYPE, nullable=True),
    Column("context", JSON_TYPE, nullable=True),
    Column("language", String(16), nullable=True),
    Column("epistemic_status", String(32), nullable=True),
    Column("provenance", JSON_TYPE, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    # Revision 0016 — §18.2: set when the record is soft-deleted; a read
    # filters on ``deleted_at IS NULL`` (partial index of the same name).
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


def to_information_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``information_units`` row onto the §11 API payload."""
    data = dict(row)
    information_id = data.get("id")
    return {
        "information_id": information_id,
        "type": data.get("type") or "text",
        "content": as_dict(data.get("content")),
        "raw_reference": as_dict(data.get("raw_reference")),
        "source_id": data.get("source_id"),
        "document_id": data.get("document_id"),
        "dataset_id": data.get("dataset_id"),
        "location": as_dict(data.get("location")),
        "context": as_dict(data.get("context")),
        "language": data.get("language"),
        "provenance": as_dict(data.get("provenance")),
        "data_stage": data.get("data_stage") or "raw",
        "epistemic_status": data.get("epistemic_status") or "factual",
        # §18.1 — a stored unit is its own first version.
        "versions": [information_id] if information_id else [],
        "created_at": as_iso(data.get("created_at")),
        "updated_at": as_iso(data.get("updated_at")),
        # Décision ``0016`` (§18.2) : la date de retrait fait partie de ce qu'une
        # lecture doit dire. Même projection que l'artefact.
        "deleted_at": as_iso(data.get("deleted_at")),
    }


class InformationUnitRepository(TableRepository):
    """Persistence of the §11 information units."""

    _metadata = information_units_metadata
    _table = information_units_table

    @classmethod
    async def get(cls, engine: Any, information_id: str) -> dict[str, Any] | None:
        """Return one information unit by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(information_units_table).where(
                    information_units_table.c.id == information_id
                )
            )
            row = result.mappings().first()
        return to_information_response(row) if row else None

    @classmethod
    async def list(
        cls,
        engine: Any,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List information units, newest first, optionally filtered by source."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            query = (
                select(information_units_table)
                .order_by(information_units_table.c.created_at.desc())
                .limit(limit)
            )
            if source_id:
                query = query.where(information_units_table.c.source_id == source_id)
            result = await conn.execute(query)
            return [to_information_response(row) for row in result.mappings().all()]

    @classmethod
    async def list_for_request(
        cls, engine: Any, request_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Return the §11 units ingested for *request_id*, newest first.

        §9.1 — a unit belongs to a request through the document it was extracted
        from: the upload endpoint writes ``document_id`` on every unit it stores,
        and ``documents`` carries the ``request_id``. That join is what answers
        "what did this request ingest?" without re-reading the file.
        """
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(information_units_table)
                .join(
                    documents_table,
                    information_units_table.c.document_id == documents_table.c.id,
                )
                .where(documents_table.c.request_id == request_id)
                .order_by(information_units_table.c.created_at.desc())
                .limit(limit)
            )
            return [to_information_response(row) for row in result.mappings().all()]

    @classmethod
    async def create(cls, engine: Any, unit: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one information unit and return its §11 representation."""
        await cls.ensure_table(engine)
        item = dict(unit)
        information_id = str(item.get("information_id") or ULID.new("INF_"))
        now = datetime.now(UTC)
        row = {
            "id": information_id,
            "type": item.get("type") or "text",
            "content": dict(item.get("content") or {}),
            "source_id": item.get("source_id") or "SRC_UNKNOWN",
            # ``document_id`` carries a foreign key to ``documents``: it is
            # written only when the caller provides one (§9.1 ingestion persists
            # the document first), never guessed.
            "document_id": item.get("document_id") or None,
            "dataset_id": item.get("dataset_id") or None,
            "location": dict(item.get("location") or {}),
            "data_stage": item.get("data_stage") or "raw",
            "raw_reference": dict(item.get("raw_reference") or {}),
            "context": dict(item.get("context") or {}),
            "language": item.get("language"),
            "epistemic_status": item.get("epistemic_status") or "factual",
            "provenance": dict(item.get("provenance") or {}),
            "created_at": as_datetime(item.get("created_at"), now),
            "updated_at": as_datetime(item.get("updated_at"), now),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(information_units_table).values(**row))
        return to_information_response(row)

    @classmethod
    async def soft_delete_by_owner(
        cls,
        engine: Any,
        *,
        dataset_id: str | None = None,
        document_id: str | None = None,
    ) -> int:
        """Retire les unités d'un dataset ou d'un document (§18.2, §41.9).

        La propagation est celle du modèle : ``information_units.dataset_id`` et
        ``information_units.document_id`` sont les deux liens réels qui
        rattachent une unité à la matière dont elle vient. Aucune suppression
        physique — ``deleted_at`` est renseigné —, donc la provenance reste
        lisible et l'unité sort simplement de l'ensemble actif (ce que la
        recherche filtre désormais).

        Args:
            engine: moteur de base de données.
            dataset_id: dataset dont les unités se retirent.
            document_id: document dont les unités se retirent.

        Returns:
            Le nombre d'unités retirées de l'ensemble actif.

        Raises:
            ValueError: quand aucun propriétaire n'est nommé (un appel sans
                cible retirerait tout ou rien, jamais ce qui est demandé).
        """
        if not dataset_id and not document_id:
            raise ValueError("dataset_id ou document_id est requis (§41.9)")
        await cls.ensure_table(engine)
        condition = (
            information_units_table.c.dataset_id == dataset_id
            if dataset_id
            else information_units_table.c.document_id == document_id
        )
        async with engine.begin() as conn:
            result = await conn.execute(
                update(information_units_table)
                .where(condition, information_units_table.c.deleted_at.is_(None))
                .values(deleted_at=datetime.now(UTC))
            )
        return int(result.rowcount or 0)

    @classmethod
    async def update_metadata(
        cls,
        engine: Any,
        information_id: str,
        *,
        provenance: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> None:
        """Remplace les métadonnées d'une unité (pseudonymisation §41.9).

        Seuls ``provenance`` et ``context`` sont touchés : le contenu, le
        ``data_stage`` et les liens de provenance de l'unité restent en place —
        c'est la structure que §41.9 exige de ne pas supprimer.

        Args:
            engine: moteur de base de données.
            information_id: l'unité à réécrire.
            provenance: la provenance pseudonymisée (déjà calculée par
                :class:`~app.governance.retention.gdpr_handler.GDPRHandler`).
            context: le contexte pseudonymisé.
        """
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                update(information_units_table)
                .where(information_units_table.c.id == information_id)
                .values(
                    provenance=dict(provenance),
                    context=dict(context),
                    updated_at=datetime.now(UTC),
                )
            )


def get_database_engine() -> Any | None:
    """Return the engine of ``INIS_DATABASE_URL``, or ``None`` (in-memory mode)."""
    return get_default_engine()
