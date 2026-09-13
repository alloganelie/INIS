"""Domain entity representing a traceable unit of information."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import ValidationError


class InformationUnit(BaseModel):
    """Information retained with source context and complete provenance."""

    information_id: str
    type: Literal["text", "number", "table", "record", "image_region", "document_fragment"]
    content: dict
    raw_reference: dict
    source_id: str
    document_id: str | None
    dataset_id: str | None
    location: dict
    context: dict
    language: str | None
    unit: str | None
    time: dict
    classification: dict
    quality: dict
    confidence: dict
    provenance: dict
    versions: list[str]
    data_stage: Literal["raw", "normalized", "enriched", "derived"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        """Enforce the provenance invariant for factual information."""
        if not self.provenance:
            raise ValidationError("InformationUnit requires provenance.")
