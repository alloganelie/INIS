"""§5.2/§9.1 — ingest a source *named by reference*, without HTTP multipart.

``POST /v1/requests/{id}/documents`` covers an HTTP client. An agent that speaks
the INIS protocol (§5.2) has no multipart to send: it names an object already
stored in the deployment's bucket (``s3://bucket/cle``) and expects the request to
own it. This module is that second door, and it is deliberately the **same**
ingestion as the upload path:

    download (streamed, bounded by §41.2) → type by content (§9.1)
    → ``sources`` + ``documents`` rows → §11 units + ``Dataset`` (§11/§27)

What it does *not* do is copy the object: the bytes are already in the bucket the
deployment owns, so the client's reference **is** the ``storage_ref`` (§18.1) and
a second copy would only create a second truth. The bucket is checked against the
configured one: a reference pointing elsewhere is refused (§19.3), never fetched.

Nothing is half-created: the caller ingests **before** the request is scheduled,
so a source INIS cannot read is reported instead of producing a request whose
material silently does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.connectors.files.mime_sniffer import require_supported
from app.core.errors import InisError, ValidationError
from app.core.hashing import sha256_hex
from app.core.size_limits import effective_max_upload_bytes
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.storage.object_storage.object_downloader import download_object_to_temp
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
    get_database_engine,
)
from app.storage.repositories.source_repository import SourceRepository

__all__ = ["IntakeResult", "intake_source_ref"]


@dataclass
class IntakeResult:
    """What the ingestion of one named object produced."""

    source_ref: str
    document_id: str
    source_id: str
    file_name: str
    mime_type: str
    size_bytes: int
    content_hash: str
    units: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Return the factual sentence describing what was ingested."""
        return (
            f"{self.file_name} ({self.mime_type}, {self.size_bytes} octets) lu depuis "
            f"{self.source_ref} : {len(self.units)} unité(s) §11 extraite(s)."
        )


async def intake_source_ref(
    *,
    request_id: str,
    source_ref: str,
    engine: Any | None = None,
    budget: Any | None = None,
) -> IntakeResult:
    """Ingest the object *source_ref* for *request_id* and return what was read.

    Args:
        request_id: The request the object belongs to.
        source_ref: ``s3://bucket/cle`` reference of the object.
        engine: Database engine; ``get_database_engine()`` when omitted (an
            unconfigured database is reported as a limitation, never hidden).
        budget: The request's §41.2 budget; its ``max_storage_bytes`` caps the
            transfer exactly as it caps an upload.

    Returns:
        The identifiers, the §11 units extracted from the object and the
        limitations of what could not be persisted.

    Raises:
        ValidationError: When the reference is malformed, names another bucket
            (§19.3), the object is empty, or its type is outside the §9.1
            whitelist.
        InfrastructureError: When object storage is not configured, or the object
            cannot be read.
    """
    ceiling = effective_max_upload_bytes(budget)
    with download_object_to_temp(source_ref, limit=ceiling) as downloaded:
        data = Path(downloaded.path).read_bytes()
        file_name = Path(downloaded.key).name or downloaded.key
        if not data:
            raise ValidationError(
                f"Objet vide ({source_ref}) : aucun octet à ingérer (§25.2)."
            )
        sniffed = require_supported(data, file_name)
        storage_ref = downloaded.uri

    document_id = ULID.new("DOC_")
    source_id = ULID.new("SRC_")
    outcome = await ingest_document(
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name=file_name,
        mime_type=sniffed.mime_type,
        data=data,
        storage_ref=storage_ref,
    )

    limitations = list(outcome.limitations)
    target = engine if engine is not None else get_database_engine()
    await _persist(
        target,
        request_id=request_id,
        document_id=document_id,
        source_id=source_id,
        file_name=file_name,
        mime_type=sniffed.mime_type,
        size_bytes=len(data),
        content_hash=sha256_hex(data),
        storage_ref=storage_ref,
        outcome=outcome,
        limitations=limitations,
    )
    return IntakeResult(
        source_ref=storage_ref,
        document_id=document_id,
        source_id=source_id,
        file_name=file_name,
        mime_type=sniffed.mime_type,
        size_bytes=len(data),
        content_hash=sha256_hex(data),
        units=list(outcome.units),
        limitations=limitations,
    )


async def _persist(
    engine: Any | None,
    *,
    request_id: str,
    document_id: str,
    source_id: str,
    file_name: str,
    mime_type: str,
    size_bytes: int,
    content_hash: str,
    storage_ref: str,
    outcome: Any,
    limitations: list[str],
) -> None:
    """Write the §9 source, the document, the dataset and the §11 units.

    A database that cannot be reached is **stated**, never skipped silently:
    without the rows the pipeline finds no material and delivers an empty colis
    without saying why (§25.2).
    """
    if engine is None:
        limitations.append(
            "Objet lu mais non persisté (INIS_DATABASE_URL non configuré) : aucune "
            "source, aucun document et aucune unité §11 ne sont consultables, le "
            "pipeline ne verra donc aucune matière pour cette requête (§9.1)."
        )
        return

    try:
        await SourceRepository.create(
            engine,
            {
                "source_id": source_id,
                "name": file_name,
                "source_type": "object_storage",
                # The reference *is* the source's location: no URL is invented.
                "url": storage_ref,
                "description": f"Objet nommé par la requête {request_id} (§5.2)",
                "status": "active",
                "metadata": {
                    "request_id": request_id,
                    "sha256": content_hash,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "named_by": "source_ref",
                },
            },
        )
        await DocumentRepository.create(
            engine,
            {
                "document_id": document_id,
                "source_id": source_id,
                "request_id": request_id,
                "file_name": file_name,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "sha256": content_hash,
                "content_hash": content_hash,
                "storage_ref": storage_ref,
                "pii_classification": {},
            },
        )
        if outcome.dataset is not None:
            await DatasetRepository.create(
                engine,
                {**outcome.dataset, "name": file_name, "request_id": request_id},
            )
        for unit in outcome.units:
            await InformationUnitRepository.create(engine, unit)
    except InisError as exc:
        limitations.append(
            f"Objet lu mais non persisté ({type(exc).__name__}: {exc}) — les unités "
            "restent publiées dans la réponse d'ingestion, elles ne sont pas "
            "consultables via l'API."
        )
    except Exception as exc:  # noqa: BLE001 - a driver error is a limitation, not a crash
        limitations.append(f"Objet lu mais non persisté ({type(exc).__name__}: {exc}).")

