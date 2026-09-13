"""Domain entity representing a document obtained from a source."""

from pydantic import BaseModel


class Document(BaseModel):
    """A stored document with source provenance and content identity."""

    document_id: str
    source_id: str
    mime_type: str
    content_hash: str
    storage_ref: str
