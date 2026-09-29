"""Deterministic ``Document`` builders (§9, §33.2)."""

from __future__ import annotations

import hashlib
from typing import Any

from app.domain.entities.document import Document
from app.domain.value_objects.ulid import ULID

#: The bytes every default document stores.
DEFAULT_BODY = b"%PDF-1.7\n% INIS test document\n"


def make_document(
    *,
    source_id: str | None = None,
    body: bytes = DEFAULT_BODY,
    **overrides: Any,
) -> Document:
    """Return a valid :class:`~app.domain.entities.document.Document`.

    Args:
        source_id: The source the document came from.
        body: Payload whose SHA-256 fills ``content_hash`` — the identity §18.1
            requires to stay stable across versions.
        **overrides: Any ``Document`` field.
    """
    values: dict[str, Any] = {
        "document_id": ULID.new("DOC_"),
        "source_id": source_id or ULID.new("SRC_"),
        "mime_type": "application/pdf",
        "content_hash": hashlib.sha256(body).hexdigest(),
        "storage_ref": "s3://inis-documents/test/document.pdf",
    }
    values.update(overrides)
    return Document(**values)

