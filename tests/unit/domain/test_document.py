"""Tests for the Document domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.document import Document


def make_document(**overrides: object) -> Document:
    values: dict[str, object] = {
        "document_id": "DOC_01H00000000000000000000000",
        "source_id": "SRC_01H00000000000000000000000",
        "mime_type": "application/pdf",
        "content_hash": "a" * 64,
        "storage_ref": "s3://inis/documents/report.pdf",
    }
    values.update(overrides)
    return Document(**values)


def test_document_valid_creation() -> None:
    document = make_document()

    assert document.source_id == "SRC_01H00000000000000000000000"
    assert document.mime_type == "application/pdf"


def test_document_requires_source_provenance() -> None:
    with pytest.raises(ValidationError):
        Document(
            document_id="DOC_01H00000000000000000000000",
            mime_type="application/pdf",
            content_hash="a" * 64,
            storage_ref="s3://inis/documents/report.pdf",
        )


def test_document_preserves_content_identity_and_storage_reference() -> None:
    document = make_document()

    assert document.content_hash == "a" * 64
    assert document.storage_ref == "s3://inis/documents/report.pdf"
