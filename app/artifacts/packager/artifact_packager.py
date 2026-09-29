"""Build the §24.2 record of one delivered file: bytes → object storage → ``Artifact``.

The packager owns the *file* side of a delivery and nothing else: the identifier
comes from :mod:`app.artifacts.packager.artifact_sequence`, the bytes from
:mod:`app.artifacts.generators`, the row itself from
:class:`app.domain.entities.artifact.Artifact`.

Failure policy (§25.1 « Résultat partiel » / §25.2 « Échec transparent »): if the
object store refuses the upload, the artifact is not silently dropped and the
delivery is not failed. The §24.2 record is returned with an ``unavailable://``
``storage_ref``, the digest and the size of the bytes it describes, and a
``limitation`` naming the cause — so the client learns that a file existed and
that it could not be retrieved, instead of discovering it through a 404.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.artifacts.generators import generate_artifact
from app.core.hashing import sha256_hex
from app.domain.entities.artifact import Artifact

__all__ = ["UNSTORED_REF_SCHEME", "ArtifactPackager", "PackageResult"]

#: Scheme written in ``storage_ref`` when the bytes could not be stored (§24.2).
UNSTORED_REF_SCHEME = "unavailable://"

#: §24.2 ``artifact_type`` of each deliverable format.
ARTIFACT_TYPES: dict[str, str] = {
    "csv": "dataset_export",
    "xlsx": "dataset_export",
    "json": "report",
    "xml": "report",
}


@dataclass(frozen=True)
class PackageResult:
    """One packaged artifact and the caveat that came with it."""

    artifact: Artifact
    content: bytes
    limitation: str | None = None

    @property
    def stored(self) -> bool:
        """Return whether the bytes are retrievable from object storage."""
        return not self.artifact.storage_ref.startswith(UNSTORED_REF_SCHEME)


class ArtifactPackager:
    """Turn a generated file into the §24.2 artifact record of a delivery."""

    def __init__(
        self,
        storage: Any | None = None,
        *,
        prefix: str = "deliveries",
    ) -> None:
        """Bind the packager to an object-store port.

        Args:
            storage: Object with ``upload(key, data, content_type=...) -> str``
                (``S3Client``, ``ObjectUploader`` or a test double). ``None``
                means "no object storage configured": the record is still built,
                and ``storage_ref`` states that the bytes were not stored.
            prefix: Key prefix of the objects this packager writes.
        """
        self._storage = storage
        self._prefix = prefix.strip("/")

    def _object_key(self, artifact_id: str, file_name: str) -> str:
        """Return the object key of one artifact (one id, one file: it is unique)."""
        return f"{self._prefix}/{artifact_id}/{file_name}"

    def package(
        self,
        *,
        artifact_id: str,
        output_format: str,
        file_stem: str,
        purpose: str,
        payload: Mapping[str, Any] | None = None,
        rows: Sequence[Mapping[str, Any]] | None = None,
        columns: Sequence[str] | None = None,
        sheets: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        source_ids: Sequence[str] = (),
        dataset_ids: Sequence[str] = (),
        transformation_ids: Sequence[str] = (),
        quality_score: float | None = None,
        confidence_score: float | None = None,
        version: str = "1.0.0",
        artifact_type: str | None = None,
    ) -> PackageResult:
        """Generate, store and describe one §24.2 artifact.

        Args:
            artifact_id: Identifier from the §24.2 sequence.
            output_format: ``csv``, ``json``, ``xml`` or ``xlsx``; ``pdf`` is
                refused by the generator (§4.1).
            file_stem: Base name of the file.
            purpose: The §24.2 ``purpose``, in the requester's words.
            payload: §24.1 delivery payload (JSON/XML).
            rows: Tabular projection of the requested dataset (CSV/XLSX).
            columns: Column order of the tabular export.
            sheets: Full §24.3 workbook description (XLSX); when omitted the
                ``data`` sheet is built from *rows*.
            source_ids: ``SRC_`` identifiers the file was derived from.
            dataset_ids: ``DATA_`` identifiers the file was derived from.
            transformation_ids: ``TRF_`` identifiers the file was derived from.
            quality_score: §13 quality score of the exported material, if any.
            confidence_score: §15 confidence score, if any.
            version: §24.2 semver of this artifact.
            artifact_type: §24.2 type; deduced from the format when omitted.

        Returns:
            A :class:`PackageResult` whose ``artifact`` is always a valid §24.2
            record, and whose ``limitation`` is set when nothing was stored.

        Raises:
            ValidationError: When the format cannot be produced (unknown,
                ``evidence_package`` or ``pdf``) — see the generator.
        """
        generated = generate_artifact(
            output_format,
            file_stem=file_stem,
            payload=payload,
            rows=rows,
            columns=columns,
            sheets=sheets,
        )

        artifact = Artifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type or ARTIFACT_TYPES.get(output_format, "other"),
            file_name=generated.file_name,
            mime_type=generated.mime_type,
            version=version,
            size_bytes=len(generated.content),
            sha256=sha256_hex(generated.content),
            storage_ref=f"{UNSTORED_REF_SCHEME}{generated.file_name}",
            purpose=purpose,
            source_ids=list(source_ids),
            dataset_ids=list(dataset_ids),
            transformation_ids=list(transformation_ids),
            quality_score=quality_score,
            confidence_score=confidence_score,
            provenance_complete=bool(source_ids or dataset_ids or transformation_ids),
            status="available",
        )

        if self._storage is None:
            return PackageResult(
                artifact=artifact,
                content=generated.content,
                limitation=(
                    f"Artefact {artifact.artifact_id} ({artifact.file_name}) non stocké : "
                    "aucun stockage objet configuré, les octets ne sont pas téléchargeables."
                ),
            )

        key = self._object_key(artifact.artifact_id, artifact.file_name)
        try:
            storage_ref = self._storage.upload(
                key, generated.content, content_type=generated.mime_type
            )
        except Exception as exc:  # noqa: BLE001 - §25.2: report, never hide
            return PackageResult(
                artifact=artifact,
                content=generated.content,
                limitation=(
                    f"Artefact {artifact.artifact_id} ({artifact.file_name}) non stocké "
                    f"({type(exc).__name__}: {exc}) — les octets ne sont pas téléchargeables."
                ),
            )

        artifact.storage_ref = str(storage_ref)
        # §24.2 — a stored artifact that claims completeness must be traceable.
        artifact.validate()
        return PackageResult(artifact=artifact, content=generated.content, limitation=None)
