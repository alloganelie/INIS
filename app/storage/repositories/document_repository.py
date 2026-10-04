"""Persistence of the uploaded/collected documents (§9.1, §18.1, §27, §32).

The table is the one revision ``0002`` created, plus the upload metadata revision
``0014`` adds (``file_name``, ``size_bytes``, ``request_id``,
``pii_classification``).

``content_hash`` is the SHA-256 of the bytes: it is the document's identity for
§18.1 (the same file uploaded twice is the same document) and it is what makes
the storage key deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
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

__all__ = ["DocumentRepository", "documents_table"]

documents_metadata = MetaData()

documents_table = Table(
    "documents",
    documents_metadata,
    Column("id", String(64), primary_key=True),
    Column("source_id", String(64), nullable=False),
    Column("mime_type", String(255), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("storage_ref", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=True),
    # Revision 0014 — the metadata an upload carries.
    Column("file_name", String(512), nullable=True),
    Column("size_bytes", BigInteger, nullable=True),
    Column("request_id", String(64), nullable=True),
    Column("pii_classification", JSON_TYPE, nullable=True),
    # Revision 0016 — §18.2: set when the record is soft-deleted; a read
    # filters on ``deleted_at IS NULL`` (partial index of the same name).
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


def to_document_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``documents`` row onto the §32 payload."""
    data = dict(row)
    return {
        "document_id": data.get("id"),
        "source_id": data.get("source_id"),
        "request_id": data.get("request_id"),
        "file_name": data.get("file_name"),
        "mime_type": data.get("mime_type"),
        "size_bytes": data.get("size_bytes"),
        "sha256": data.get("content_hash"),
        "storage_ref": data.get("storage_ref"),
        "pii_classification": as_dict(data.get("pii_classification")),
        "created_at": as_iso(data.get("created_at")),
        # Décision ``0016`` (§18.2) : la date de retrait fait partie de ce qu'une
        # lecture doit dire. Même projection que l'artefact.
        "deleted_at": as_iso(data.get("deleted_at")),
    }


class DocumentRepository(TableRepository):
    """Persistence of the §9 documents."""

    _metadata = documents_metadata
    _table = documents_table

    @classmethod
    async def get(cls, engine: Any, document_id: str) -> dict[str, Any] | None:
        """Return one document by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(documents_table).where(documents_table.c.id == document_id)
            )
            row = result.mappings().first()
        return to_document_response(row) if row else None

    @classmethod
    async def find_by_content(
        cls,
        engine: Any,
        *,
        request_id: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """Return the document already stored for these bytes, or ``None``.

        Used to make an upload idempotent: re-sending the same file for the same
        request must return the existing document, not create a second one.
        """
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(documents_table).where(
                    documents_table.c.request_id == request_id,
                    documents_table.c.content_hash == content_hash,
                )
            )
            row = result.mappings().first()
        return to_document_response(row) if row else None

    @classmethod
    async def list_for_request(
        cls,
        engine: Any,
        request_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return the documents uploaded for *request_id*, newest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(documents_table)
                .where(documents_table.c.request_id == request_id)
                .order_by(documents_table.c.created_at.desc(), documents_table.c.id.desc())
                .limit(limit)
            )
            rows = result.mappings().all()
        return [to_document_response(row) for row in rows]

    @classmethod
    async def list_all(cls, engine: Any, limit: int = 100) -> list[dict[str, Any]]:
        """Return the documents of the instance, newest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(documents_table)
                .order_by(documents_table.c.created_at.desc(), documents_table.c.id.desc())
                .limit(limit)
            )
            rows = result.mappings().all()
        return [to_document_response(row) for row in rows]

    @classmethod
    async def create(cls, engine: Any, record: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one document and return its §32 representation.

        Idempotent on the document's identity: when a row already exists for the
        same ``request_id`` and ``content_hash``, it is returned instead of
        raising on the unique constraint (CODING_RULES §1.10).
        """
        await cls.ensure_table(engine)
        document_id = str(record.get("document_id") or record.get("id") or "")
        if not document_id:
            raise ValueError("document_id is required to persist a document (§9.1)")
        request_id = record.get("request_id")
        content_hash = str(record.get("content_hash") or record.get("sha256") or "")
        if request_id and content_hash:
            existing = await cls.find_by_content(
                engine, request_id=str(request_id), content_hash=content_hash
            )
            if existing is not None:
                return existing

        size_bytes = record.get("size_bytes")
        row: dict[str, Any] = {
            "id": document_id,
            "source_id": str(record.get("source_id") or ""),
            "mime_type": str(record.get("mime_type") or "application/octet-stream"),
            "content_hash": content_hash,
            "storage_ref": str(record.get("storage_ref") or ""),
            "created_at": as_datetime(record.get("created_at"), datetime.now(UTC)),
            "file_name": record.get("file_name"),
            "size_bytes": int(size_bytes) if size_bytes is not None else None,
            "request_id": request_id,
            "pii_classification": dict(record.get("pii_classification") or {}),
        }
        async with engine.begin() as conn:
            await conn.execute(insert(documents_table).values(**row))
        return to_document_response(row)

    @classmethod
    async def soft_delete(cls, engine: Any, document_id: str) -> dict[str, Any] | None:
        """Remove one document from the active set (§18.2, décision ``0016``).

        Aucune suppression physique : ``deleted_at`` est renseigné, la ligne et
        son ``storage_ref`` restent lisibles. Les unités extraites de ce document
        se retirent par ``InformationUnitRepository.soft_delete_by_owner`` : la
        suppression se propage le long de la chaîne de provenance (§41.9).

        Args:
            engine: moteur de base de données.
            document_id: le document à retirer de l'ensemble actif.

        Returns:
            Le document relu (marqué), ou ``None`` s'il n'existe pas.
        """
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                update(documents_table)
                .where(
                    documents_table.c.id == document_id,
                    documents_table.c.deleted_at.is_(None),
                )
                .values(deleted_at=datetime.now(UTC))
            )
            if not result.rowcount:
                return None
        return await cls.get(engine, document_id)
