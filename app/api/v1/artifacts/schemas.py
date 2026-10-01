"""Wire schemas of the §24.2 delivered artifacts (§32).

Field names are the canonical §24.2 ones (``file_name``, ``mime_type``,
``storage_ref``) — NAMING.md keeps the backend canonical and asks the frontend
to map explicitly when it needs another shape. ``request_id`` and ``created_at``
are added by the contract of *this* endpoint: §24.2 describes the file, the
request link is what makes it findable again.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ArtifactDeliveryEventResponse",
    "ArtifactLineageResponse",
    "ArtifactLineageView",
    "ArtifactList",
    "ArtifactResponse",
    "ArtifactVersionList",
    "ArtifactVersionResponse",
]


class ArtifactResponse(BaseModel):
    """One §24.2 artifact as the API exposes it."""

    artifact_id: str
    request_id: str | None = None
    artifact_type: str
    file_name: str
    mime_type: str
    version: str = "1.0.0"
    size_bytes: int = 0
    sha256: str = ""
    storage_ref: str = ""
    purpose: str = ""
    source_ids: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    transformation_ids: list[str] = Field(default_factory=list)
    quality_score: float | None = None
    confidence_score: float | None = None
    provenance_complete: bool = False
    status: str = "available"
    created_at: str | None = None


class ArtifactList(BaseModel):
    """The artifacts of one request (or of the instance)."""

    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    total: int = 0


class ArtifactLineageResponse(BaseModel):
    """The inputs one artifact version was derived from (§24.2)."""

    artifact_lineage_id: str
    artifact_id: str
    source_ids: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    transformation_ids: list[str] = Field(default_factory=list)


class ArtifactVersionResponse(BaseModel):
    """One version of an artifact, with the lineage of that version (§18.1)."""

    artifact_version_id: str
    artifact_id: str
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    lineage: ArtifactLineageResponse | None = None


class ArtifactDeliveryEventResponse(BaseModel):
    """One delivery of an artifact's bytes (§24.3)."""

    delivery_event_id: str
    artifact_id: str
    target: str
    status: str
    delivered_at: str | None = None
    created_at: str | None = None


class ArtifactVersionList(BaseModel):
    """The version history of one artifact, and which version is current."""

    artifact_id: str
    current_version: str | None = None
    versions: list[ArtifactVersionResponse] = Field(default_factory=list)


class ArtifactLineageView(BaseModel):
    """The whole chain of one artifact: per-version lineage and deliveries."""

    artifact_id: str
    versions: list[ArtifactVersionResponse] = Field(default_factory=list)
    delivery_events: list[ArtifactDeliveryEventResponse] = Field(default_factory=list)
