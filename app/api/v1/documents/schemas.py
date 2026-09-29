"""Wire schemas of the §9.1 document ingestion (§18.1, §19.4, §32).

``sha256`` is the canonical name on the wire: it *is* the ``content_hash`` column
(§18.1), and the API exposes it as the digest a client can verify — the same name
the §24.2 artifact record uses for the same reason.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = ["DocumentList", "DocumentResponse", "DocumentUploadResponse", "PiiClassification"]


class PiiClassification(BaseModel):
    """§19.4 classification of what was received (name, metadata)."""

    sensitivity: str = "low"
    pii: bool = False
    categories: list[str] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    """One stored document as the API exposes it."""

    document_id: str
    source_id: str
    request_id: str | None = None
    file_name: str | None = None
    mime_type: str
    size_bytes: int | None = None
    sha256: str
    storage_ref: str
    pii_classification: PiiClassification = Field(default_factory=PiiClassification)
    created_at: str | None = None


class DocumentUploadResponse(DocumentResponse):
    """The document that was accepted, plus what the ingestion did with it."""

    #: ``True`` when these exact bytes were already stored for this request.
    idempotent: bool = False
    #: §11 units extracted from the document (empty until the extraction path is wired).
    information_units: list[dict[str, Any]] = Field(default_factory=list)
    #: §25.2 — what did not happen, stated explicitly.
    limitations: list[str] = Field(default_factory=list)


class DocumentList(BaseModel):
    """The documents of one request (or of the instance)."""

    documents: list[DocumentResponse] = Field(default_factory=list)
    total: int = 0
