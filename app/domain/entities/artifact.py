"""Domain entities for delivered artifacts (§24.2).

An artifact is a *file* INIS delivered — a dataset export, a report, a document.
§24.2 fixes its contract; the ``artifacts`` / ``artifact_versions`` /
``artifact_lineage`` tables of revision ``0005`` persist it. The three entities
below are the domain side of that contract:

* :class:`Artifact` — the §24.2 record itself;
* :class:`ArtifactVersion` — an immutable successive version of the same file;
* :class:`ArtifactLineage` — the source/dataset/transformation identifiers the
  artifact was derived from.

``artifact_id`` follows the §24.2 ``ART_{YYYY}_{SEQ6}`` format, which is *not* a
ULID, so it is validated by pattern while the identifiers it points to keep the
§0.3 ``SRC_``/``DATA_``/``TRF_`` prefixes.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.errors import ValidationError

__all__ = [
    "ARTIFACT_STATUSES",
    "ARTIFACT_TYPES",
    "Artifact",
    "ArtifactLineage",
    "ArtifactVersion",
]

#: The §24.2 allowed artifact types.
ARTIFACT_TYPES: tuple[str, ...] = ("dataset_export", "report", "document", "other")

#: The §24.2 lifecycle statuses.
ARTIFACT_STATUSES: tuple[str, ...] = ("available", "archived", "deleted")

#: ``ART_{YYYY}_{SEQ6}`` — the §24.2 identifier format.
_ARTIFACT_ID_PATTERN = re.compile(r"^ART_\d{4}_\d{6}$")

#: ``<major>.<minor>.<patch>`` — the §24.2 ``version`` format.
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _require_prefixed(value: str, prefix: str, field_name: str) -> str:
    """Return *value* when it starts with ``prefix``, else raise ``ValueError``."""
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(f"{field_name} must start with '{prefix}' (§0.3)")
    return value


class Artifact(BaseModel):
    """One delivered file, exactly as §24.2 describes it."""

    artifact_id: str
    artifact_type: Literal["dataset_export", "report", "document", "other"]
    file_name: str
    mime_type: str
    version: str = "1.0.0"
    size_bytes: int = Field(ge=0)
    sha256: str
    storage_ref: str
    purpose: str
    source_ids: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    transformation_ids: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance_complete: bool = False
    status: Literal["available", "archived", "deleted"] = "available"

    @field_validator("artifact_id")
    @classmethod
    def _validate_artifact_id(cls, value: str) -> str:
        """Require the §24.2 ``ART_{YYYY}_{SEQ6}`` format."""
        if not _ARTIFACT_ID_PATTERN.match(value or ""):
            raise ValueError("artifact_id must match ART_{YYYY}_{SEQ6} (§24.2)")
        return value

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        """Require a semantic ``major.minor.patch`` version."""
        if not _SEMVER_PATTERN.match(value or ""):
            raise ValueError("version must be a semver string (§24.2)")
        return value

    @field_validator("source_ids")
    @classmethod
    def _validate_source_ids(cls, value: list[str]) -> list[str]:
        """Require every referenced source to be a ``SRC_`` identifier (§0.3)."""
        for source_id in value:
            _require_prefixed(source_id, "SRC_", "source_ids[]")
        return value

    @field_validator("dataset_ids")
    @classmethod
    def _validate_dataset_ids(cls, value: list[str]) -> list[str]:
        """Require every referenced dataset to be a ``DATA_`` identifier (§0.3)."""
        for dataset_id in value:
            _require_prefixed(dataset_id, "DATA_", "dataset_ids[]")
        return value

    @field_validator("transformation_ids")
    @classmethod
    def _validate_transformation_ids(cls, value: list[str]) -> list[str]:
        """Require every referenced transformation to be a ``TRF_`` id (§0.3)."""
        for transformation_id in value:
            _require_prefixed(transformation_id, "TRF_", "transformation_ids[]")
        return value

    def validate(self) -> None:
        """Enforce the §24.2 requirement that a delivered file is traceable.

        Raises:
            ValidationError: when ``provenance_complete`` is claimed while no
                source, dataset or transformation backs the artifact.
        """
        if self.provenance_complete and not (
            self.source_ids or self.dataset_ids or self.transformation_ids
        ):
            raise ValidationError(
                "Artifact cannot claim provenance_complete without a source, "
                "dataset or transformation (§24.2)."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the exact §24.2 JSON projection."""
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "version": self.version,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "storage_ref": self.storage_ref,
            "purpose": self.purpose,
            "source_ids": list(self.source_ids),
            "dataset_ids": list(self.dataset_ids),
            "transformation_ids": list(self.transformation_ids),
            "quality_score": self.quality_score,
            "confidence_score": self.confidence_score,
            "provenance_complete": self.provenance_complete,
            "status": self.status,
        }


class ArtifactVersion(BaseModel):
    """One immutable version row of an artifact (§18.1, ``artifact_versions``)."""

    artifact_version_id: str
    artifact_id: str
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        """Require a semantic ``major.minor.patch`` version."""
        if not _SEMVER_PATTERN.match(value or ""):
            raise ValueError("version must be a semver string (§24.2)")
        return value


class ArtifactLineage(BaseModel):
    """The inputs an artifact was derived from (``artifact_lineage``, §24.2)."""

    artifact_lineage_id: str
    artifact_id: str
    source_ids: list[str] = Field(default_factory=list)
    dataset_ids: list[str] = Field(default_factory=list)
    transformation_ids: list[str] = Field(default_factory=list)

    def is_complete(self) -> bool:
        """Return whether at least one input is recorded (§24.2)."""
        return bool(self.source_ids or self.dataset_ids or self.transformation_ids)
