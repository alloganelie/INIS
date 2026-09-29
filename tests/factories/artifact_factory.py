"""Deterministic §24.2 artifact builders (§24.2, §33.2)."""

from __future__ import annotations

import hashlib
from typing import Any

from app.domain.entities.artifact import Artifact, ArtifactVersion
from app.domain.value_objects.ulid import ULID

#: The bytes every default artifact stores.
DEFAULT_BODY = b"city,population\nParis,2145906\n"

#: A counter backing the ``ART_{YYYY}_{SEQ6}`` sequence of §24.2.
_SEQUENCE = {"value": 0}


def next_artifact_id(year: int = 2026) -> str:
    """Return the next in-process ``ART_{YYYY}_{SEQ6}`` identifier (§24.2)."""
    _SEQUENCE["value"] += 1
    return f"ART_{year}_{_SEQUENCE['value']:06d}"


def make_artifact(
    *,
    body: bytes = DEFAULT_BODY,
    provenance_complete: bool = True,
    **overrides: Any,
) -> Artifact:
    """Return a valid §24.2 :class:`~app.domain.entities.artifact.Artifact`.

    Args:
        body: Payload whose SHA-256 fills ``sha256``.
        provenance_complete: Kept callable so a test can build the §24.2
            inconsistency the entity refuses (loss of traceability).
        **overrides: Any ``Artifact`` field.
    """
    values: dict[str, Any] = {
        "artifact_id": next_artifact_id(),
        "artifact_type": "dataset_export",
        "file_name": "cities.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "version": "1.0.0",
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "storage_ref": "s3://inis-artifacts/test/cities.xlsx",
        "purpose": "Export of the researched dataset for the requester.",
        "source_ids": [ULID.new("SRC_")],
        "dataset_ids": [ULID.new("DATA_")],
        "transformation_ids": [ULID.new("TRF_")],
        "quality_score": 0.9,
        "confidence_score": 0.8,
        "provenance_complete": provenance_complete,
        "status": "available",
    }
    values.update(overrides)
    return Artifact(**values)


def make_artifact_version(
    artifact_id: str | None = None,
    **overrides: Any,
) -> ArtifactVersion:
    """Return one ``artifact_versions`` row (§18.1, §24.2)."""
    values: dict[str, Any] = {
        "artifact_version_id": ULID.new("VER_"),
        "artifact_id": artifact_id or next_artifact_id(),
        "version": "1.0.0",
        "metadata": {"generated_by": "inis.artifacts"},
    }
    values.update(overrides)
    return ArtifactVersion(**values)

