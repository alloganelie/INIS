"""Pydantic schemas for Information Units per §11 and §32."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class InformationUnitCreate(BaseModel):
    """Payload to create or ingest an Information Unit."""

    type: Literal[
        "text",
        "number",
        "table",
        "record",
        "image_region",
        "document_fragment",
    ] = "text"
    content: dict[str, Any] = Field(default_factory=dict, description="Extracted factual payload")
    raw_reference: dict[str, Any] = Field(default_factory=dict, description="Raw reference and offsets")
    source_id: str = Field(..., min_length=1, description="Originating source ID (SRC_...)")
    document_id: str | None = Field(default=None, description="Optional parent document ID (DOC_...)")
    dataset_id: str | None = Field(default=None, description="Optional dataset ID (DATA_...)")
    location: dict[str, Any] = Field(default_factory=dict, description="Location within the source/document")
    context: dict[str, Any] = Field(default_factory=dict, description="Surrounding contextual data")
    language: str | None = Field(default=None, description="Language code")
    unit: str | None = Field(default=None, description="Measurement unit if applicable")
    time: dict[str, Any] = Field(default_factory=dict, description="Temporal metadata")
    classification: dict[str, Any] = Field(default_factory=dict, description="Security/content classification")
    quality: dict[str, Any] = Field(default_factory=dict, description="Quality evaluation metrics")
    confidence: dict[str, Any] = Field(default_factory=dict, description="Confidence evaluation metrics")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Traceability and origin records")
    data_stage: Literal["raw", "normalized", "enriched", "derived"] = "raw"
    epistemic_status: Literal["factual", "hypothesis", "assumption", "intention", "uncertainty"] = "factual"


class InformationUnitResponse(BaseModel):
    """Full representation of an Information Unit per §11."""

    information_id: str = Field(..., description="Canonical INF_ prefixed ULID")
    type: Literal[
        "text",
        "number",
        "table",
        "record",
        "image_region",
        "document_fragment",
    ] = "text"
    content: dict[str, Any] = Field(default_factory=dict)
    raw_reference: dict[str, Any] = Field(default_factory=dict)
    source_id: str
    document_id: str | None = None
    dataset_id: str | None = None
    location: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    language: str | None = None
    unit: str | None = None
    time: dict[str, Any] = Field(default_factory=dict)
    classification: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    data_stage: str = "raw"
    epistemic_status: str = "factual"
    versions: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class InformationList(BaseModel):
    """List container for information units."""

    units: list[InformationUnitResponse] = Field(default_factory=list)
    items: list[InformationUnitResponse] = Field(default_factory=list)
    total: int = 0

    def __init__(self, **data: Any) -> None:
        if "units" in data and "items" not in data:
            data["items"] = data["units"]
        elif "items" in data and "units" not in data:
            data["units"] = data["items"]
        if "total" not in data:
            data["total"] = len(data.get("units", []))
        super().__init__(**data)
