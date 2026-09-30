"""Router for the §9.1 document ingestion (§19.4, §32, §36.6, §36.7).

Before this router existed, ``UploadFile`` had **zero occurrence** in ``app/``:
a client could state an objective and INIS would search the web, but nothing
could hand INIS a *file*. The two routes below close that hole:

* ``POST /v1/requests/{request_id}/documents`` — multipart upload;
* ``GET  /v1/documents?request_id=…`` and ``GET /v1/documents/{document_id}`` —
  read back what was accepted.

Rules this router enforces, because each of them was a way to lie:

* the request must exist, otherwise the upload is refused with a **404** (an
  orphan document is unpublishable);
* the type is decided by the **bytes**, never by the extension (§9.1) and a type
  outside the whitelist is refused with the detected type named;
* the size is checked against the §41.2 storage budget of the request, streamed
  so an oversized body is refused *before* being held in memory;
* the binary must be stored: without object storage the upload is a **503**
  (silently dropping the file would make the document unreadable forever);
* §19.4 classification of the name and metadata is computed and **recorded**;
* the same bytes uploaded twice for the same request return the same document
  (idempotent), never a duplicate.

What is *not* done yet is stated, not hidden: no information unit is extracted
from the document (the extraction path is the next step of L2), so the response
carries ``information_units: []`` and a ``limitation`` saying so.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.api.v1.documents.schemas import DocumentList, DocumentResponse, DocumentUploadResponse
from app.api.v1.requests.router import _REQUESTS_STORE
from app.connectors.files.mime_sniffer import require_supported
from app.connectors.files.upload_policy import effective_max_upload_bytes, overflow_message
from app.core.errors import ValidationError
from app.core.hashing import sha256_hex
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.security.pii.sensitivity_classifier import SensitivityClassifier
from app.storage.object_storage.object_storage_factory import build_object_storage
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
    get_database_engine,
)
from app.storage.repositories.source_repository import SourceRepository

#: Upload + read router (``/v1/requests/{id}/documents``).
router = APIRouter(prefix="/requests", tags=["documents"])

#: Read router (``/v1/documents…``).
documents_router = APIRouter(prefix="/documents", tags=["documents"])

#: Read size of one chunk while streaming the upload towards the size ceiling.
READ_CHUNK_BYTES = 1024 * 1024


def _request_or_404(request_id: str) -> Any:
    """Return the stored request, or raise the §32 ``404``."""
    if request_id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{request_id}' not found",
        )
    return _REQUESTS_STORE[request_id]


async def _read_within_limit(upload: UploadFile, limit: int) -> bytes:
    """Return the uploaded bytes, refusing anything above *limit*.

    The body is read in chunks and the read stops one byte after the ceiling, so
    an oversized upload is answered with a ``413`` without ever being buffered
    whole in memory.
    """
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=overflow_message(limit, received),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _classification(file_name: str, source_name: str | None) -> dict[str, Any]:
    """Return the §19.4 classification of the received name and metadata.

    This runs on the name the **client sent**, not on the sanitized stored name:
    sanitizing replaces ``@`` with ``_``, which would erase an email address
    *before* it could be reported as PII. What was received is classified; what
    is stored is redacted — the two must not be confused.
    """
    classifier = SensitivityClassifier()
    return classifier.classify(f"{file_name} {source_name or ''}".strip())


@router.post(
    "/{request_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for an Information Request (§9.1, §36.6)",
)
async def upload_document(
    request_id: str,
    file: Annotated[UploadFile, File(description="Document to ingest")],
    source_name: Annotated[
        str | None, Form(description="Human label of the origin")
    ] = None,
) -> DocumentUploadResponse:
    """Accept a file, store it, classify it and describe what was received.

    Raises:
        HTTPException: 404 unknown request, 413 over the storage budget, 415
            unsupported type, 422 empty file, 503 object storage unavailable.
    """
    request = _request_or_404(request_id)
    limit = effective_max_upload_bytes(getattr(request, "budget", None))
    data = await _read_within_limit(file, limit)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document vide : aucun octet reçu, il n'y a rien à ingérer (§25.2).",
        )

    try:
        sniffed = require_supported(data, file.filename)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc

    digest = sha256_hex(data)
    limitations: list[str] = []
    engine = get_database_engine()

    # Idempotence: the same bytes for the same request are one document (§18.1).
    if engine is not None:
        existing = await DocumentRepository.find_by_content(
            engine, request_id=request_id, content_hash=digest
        )
        if existing is not None:
            return DocumentUploadResponse(
                **existing,
                idempotent=True,
                information_units=[],
                limitations=[
                    (
                        "Ces octets étaient déjà enregistrés pour cette requête "
                        f"(document {existing['document_id']}) : aucun doublon créé, aucun "
                        "second téléversement, et les unités §11 ne sont pas ré-extraites "
                        "(elles restent celles de ce document)."
                    )
                ],
            )

    document_id = ULID.new("DOC_")
    file_name = sniffed.safe_file_name(file.filename, fallback_stem=document_id)

    storage = build_object_storage()
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Stockage objet non configuré (S3_ENDPOINT, S3_ACCESS_KEY, "
                "S3_SECRET_KEY, S3_BUCKET) : le document ne serait pas relisible, "
                "l'envoi est refusé (§25.2)."
            ),
        )

    # §18.1 — the key is derived from the content: the same bytes always land on
    # the same object, so a retried upload cannot fork the stored copy.
    key = f"documents/{request_id}/{digest}{sniffed.extension}"
    storage_ref = str(storage.upload(key, data, content_type=sniffed.mime_type))

    classification = _classification(file.filename or file_name, source_name)
    source_id = await _ensure_source(
        engine,
        document_id=document_id,
        file_name=file_name,
        source_name=source_name,
        request_id=request_id,
        mime_type=sniffed.mime_type,
        digest=digest,
        size_bytes=len(data),
        classification=classification,
        limitations=limitations,
    )

    record: dict[str, Any] = {
        "document_id": document_id,
        "source_id": source_id,
        "request_id": request_id,
        "file_name": file_name,
        "mime_type": sniffed.mime_type,
        "size_bytes": len(data),
        "sha256": digest,
        "content_hash": digest,
        "storage_ref": storage_ref,
        "pii_classification": classification,
    }

    if engine is not None:
        try:
            stored = await DocumentRepository.create(engine, record)
        except Exception as exc:  # noqa: BLE001 - §25.2: the gap is named
            limitations.append(
                f"Document non persisté ({type(exc).__name__}: {exc}) — le binaire est "
                f"stocké sous {storage_ref} mais aucun enregistrement n'est conservé."
            )
            stored = record
    else:
        limitations.append(
            "Document non persisté (INIS_DATABASE_URL non configuré) — le binaire est "
            f"stocké sous {storage_ref} mais aucun enregistrement n'est conservé."
        )
        stored = record

    # ------------------------------------------------------------------
    # §11 — extract the units the document carries, and the dataset if it is
    # tabular. Nothing is invented: an unreadable payload returns no unit and
    # one limitation naming the cause. Beyond the ADR 007 threshold the
    # extraction works chunk by chunk (§41.6), which is why it is awaited.
    # ------------------------------------------------------------------
    ingestion = await ingest_document(
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name=file_name,
        mime_type=sniffed.mime_type,
        data=data,
        storage_ref=storage_ref,
    )
    limitations.extend(ingestion.limitations)

    if engine is not None and (ingestion.units or ingestion.dataset):
        try:
            if ingestion.dataset is not None:
                await DatasetRepository.create(
                    engine,
                    {
                        **ingestion.dataset,
                        "name": file_name,
                        "request_id": request_id,
                    },
                )
            for unit in ingestion.units:
                await InformationUnitRepository.create(engine, unit)
        except Exception as exc:  # noqa: BLE001 - §25.2: the gap is named
            limitations.append(
                f"Unités et/ou dataset non persistés ({type(exc).__name__}: {exc}) — ils "
                "restent publiés dans cette réponse mais ne sont pas consultables via l'API."
            )

    return DocumentUploadResponse(
        **{k: v for k, v in stored.items() if k in DocumentResponse.model_fields},
        idempotent=False,
        information_units=ingestion.units,
        limitations=limitations,
    )


async def _ensure_source(
    engine: Any | None,
    *,
    document_id: str,
    file_name: str,
    source_name: str | None,
    request_id: str,
    mime_type: str,
    digest: str,
    size_bytes: int,
    classification: dict[str, Any],
    limitations: list[str],
) -> str:
    """Register the §9 source of an uploaded document and return its identifier.

    An upload is a source like any other (§9): without a ``sources`` row the
    document cannot be persisted (the foreign key is NOT NULL), so a failure here
    is stated instead of producing an orphan.
    """
    source_id = ULID.new("SRC_")
    if engine is None:
        limitations.append(
            "Source non persistée (INIS_DATABASE_URL non configuré) : aucun "
            "enregistrement de source n'a été créé."
        )
        return source_id

    try:
        source = await SourceRepository.create(
            engine,
            {
                "source_id": source_id,
                "name": source_name or file_name,
                "source_type": "file_upload",
                # An uploaded file has no URL: the scheme states what it is
                # instead of inventing one (§37).
                "url": f"upload://{document_id}",
                "description": f"Document téléversé pour la requête {request_id}",
                "status": "active",
                "metadata": {
                    "request_id": request_id,
                    "sha256": digest,
                    "size_bytes": size_bytes,
                    "mime_type": mime_type,
                    "pii_classification": classification,
                },
            },
        )
        return str(source["source_id"])
    except Exception as exc:  # noqa: BLE001 - §25.2: the gap is named
        limitations.append(
            f"Source non persistée ({type(exc).__name__}: {exc}) — l'identifiant "
            f"{source_id} n'existe pas en base."
        )
        return source_id


@documents_router.get(
    "",
    response_model=DocumentList,
    summary="List stored documents, optionally filtered by request_id (§9.1)",
)
async def list_documents(
    request_id: str | None = Query(default=None, description="Filter by request_id"),
    limit: int = Query(default=100, ge=1, le=500),
) -> DocumentList:
    """Return the documents of a request (or all of them)."""
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Documents non persistés (INIS_DATABASE_URL non configuré) : aucun "
                "enregistrement n'est conservé, il n'y a rien à lister."
            ),
        )

    if request_id:
        rows = await DocumentRepository.list_for_request(engine, request_id, limit)
    else:
        rows = await DocumentRepository.list_all(engine, limit)
    items = [DocumentResponse(**row) for row in rows]
    return DocumentList(documents=items, total=len(items))


@documents_router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get one document by ID (§9.1)",
)
async def get_document(document_id: str) -> DocumentResponse:
    """Return one stored document, or 404 when it was never accepted."""
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Documents non persistés (INIS_DATABASE_URL non configuré) : le "
                "document ne peut pas être retrouvé."
            ),
        )

    record = await DocumentRepository.get(engine, document_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return DocumentResponse(**record)
