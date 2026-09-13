"""Pydantic schemas for Evidence per §14.2 and §32."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceCreate(BaseModel):
    """Payload to create or record an Evidence."""

    claim_id: str | None = Field(default=None, description="Associated claim ID (CLM_...)")
    information_id: str | None = Field(default=None, description="Associated information unit ID (INF_...)")
    source_id: str | None = Field(default=None, description="Source ID (SRC_...)")
    document_id: str | None = Field(default=None, description="Parent document ID (DOC_...)")
    dataset_id: str | None = Field(default=None, description="Dataset ID (DATA_...)")
    transformation_id: str | None = Field(default=None, description="Transformation ID (TRF_...)")
    excerpt: str | None = Field(default=None, description="Excerpt from the source")
    location: dict[str, Any] = Field(default_factory=dict, description="Location within document or source")
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Strength of the evidence (0-1)")
    confidence: dict[str, Any] = Field(default_factory=dict, description="Confidence metrics")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Provenance metadata")
    epistemic_status: str = Field(default="fact", description="Epistemic status")


class EvidenceResponse(BaseModel):
    """Full representation of an Evidence per §14.2."""

    evidence_id: str = Field(..., description="Canonical EVID_ prefixed ULID")
    claim_id: str | None = None
    information_id: str | None = None
    source_id: str | None = None
    document_id: str | None = None
    dataset_id: str | None = None
    transformation_id: str | None = None
    excerpt: str | None = None
    location: dict[str, Any] = Field(default_factory=dict)
    strength: float = 1.0
    confidence: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    epistemic_status: str = "fact"
    created_at: str | None = None


class EvidenceList(BaseModel):
    """Container for a list of evidence items."""

    items: list[EvidenceResponse] = Field(default_factory=list)
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    total: int = 0

    def __init__(self, **data: Any) -> None:
        if "items" in data and "evidence" not in data:
            data["evidence"] = data["items"]
        elif "evidence" in data and "items" not in data:
            data["items"] = data["evidence"]
        if "total" not in data:
            data["total"] = len(data.get("items", []))
        super().__init__(**data)
