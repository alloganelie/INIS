"""Domain entity representing a traceable unit of information."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import ValidationError
from app.core.time import utc_now


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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # -- §41.3 language metadata ---------------------------------------
    source_language: str | None = None
    normalized_language: str | None = None
    translation_applied: bool = False
    translation_model: str | None = None
    translation_transformation_id: str | None = None

    def validate(self) -> None:
        """Enforce the provenance invariant for factual information."""
        if not self.provenance:
            raise ValidationError("InformationUnit requires provenance.")
        # §41.3 — a translated unit is a derived value and must reference the
        # transformation that produced it (§12.1, §0.3).
        if self.translation_applied:
            if not self.translation_model:
                raise ValidationError(
                    "translated InformationUnit requires translation_model."
                )
            if not self.translation_transformation_id:
                raise ValidationError(
                    "translated InformationUnit requires translation_transformation_id."
                )
            from app.domain.value_objects.ulid import ULID

            if not str(self.translation_transformation_id).startswith("TRF_") or not ULID.is_valid(
                str(self.translation_transformation_id)
            ):
                raise ValidationError(
                    "translation_transformation_id must be a TRF_{ULID} identifier."
                )
