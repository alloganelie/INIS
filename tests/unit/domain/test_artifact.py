"""§24.2 — the artifact contract for every file INIS delivers.

An artifact is a delivered file: a dataset export, a report, a document. §24.2
fixes its fields; the tests below pin the three properties that make it usable
rather than merely well-formed — a canonical ``ART_{YYYY}_{SEQ6}`` identifier, a
versioned file, and a traceability claim that is actually backed by an input.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError
from app.domain.entities.artifact import (
    ARTIFACT_STATUSES,
    ARTIFACT_TYPES,
    ArtifactLineage,
    ArtifactVersion,
)
from app.domain.value_objects.ulid import ULID
from tests.factories import make_artifact, make_artifact_version


class TestArtifactContract:
    """§24.2 — the delivered file and its §24.2 projection."""

    def test_projection_carries_every_section_24_2_field(self) -> None:
        """``to_dict`` exposes exactly the §24.2 keys."""
        artifact = make_artifact()

        assert set(artifact.to_dict()) == {
            "artifact_id",
            "artifact_type",
            "file_name",
            "mime_type",
            "version",
            "size_bytes",
            "sha256",
            "storage_ref",
            "purpose",
            "source_ids",
            "dataset_ids",
            "transformation_ids",
            "quality_score",
            "confidence_score",
            "provenance_complete",
            "status",
        }

    def test_size_and_hash_describe_the_stored_bytes(self) -> None:
        """``size_bytes``/``sha256`` are the identity of the stored file (§18.1)."""
        body = b"a,b\n1,2\n"
        artifact = make_artifact(body=body)

        assert artifact.size_bytes == len(body)
        assert len(artifact.sha256) == 64

    @pytest.mark.parametrize("artifact_type", ARTIFACT_TYPES)
    def test_documented_types_are_accepted(self, artifact_type: str) -> None:
        """§24.2 lists four artifact types."""
        assert make_artifact(artifact_type=artifact_type).artifact_type == artifact_type

    @pytest.mark.parametrize("status", ARTIFACT_STATUSES)
    def test_documented_statuses_are_accepted(self, status: str) -> None:
        """§24.2 lists three lifecycle statuses."""
        assert make_artifact(status=status).status == status


class TestArtifactIdentifiers:
    """§0.3 + §24.2 — identifiers and versions are machine-checkable."""

    @pytest.mark.parametrize(
        "bad_id",
        ["ART_2026_1", "ART_26_000001", "ART_2026_000001X", "art_2026_000001"],
    )
    def test_artifact_id_must_match_the_section_24_2_format(self, bad_id: str) -> None:
        """``artifact_id`` is ``ART_{YYYY}_{SEQ6}``, not a ULID (§24.2)."""
        with pytest.raises(PydanticValidationError):
            make_artifact(artifact_id=bad_id)

    @pytest.mark.parametrize("bad_version", ["1.0", "v1.0.0", "1.0.0-rc1"])
    def test_version_must_be_semver(self, bad_version: str) -> None:
        """The §24.2 version format is ``major.minor.patch``."""
        with pytest.raises(PydanticValidationError):
            make_artifact(version=bad_version)

    def test_referenced_identifiers_keep_their_section_0_3_prefix(self) -> None:
        """An artifact points at ``SRC_``/``DATA_``/``TRF_`` identifiers only."""
        with pytest.raises(PydanticValidationError):
            make_artifact(source_ids=[ULID.new("INF_")])
        with pytest.raises(PydanticValidationError):
            make_artifact(dataset_ids=[ULID.new("DOC_")])
        with pytest.raises(PydanticValidationError):
            make_artifact(transformation_ids=[ULID.new("SRC_")])


class TestArtifactTraceability:
    """§0.2 + §24.2 — a delivery cannot claim provenance it does not have."""

    def test_provenance_claim_requires_an_input(self) -> None:
        """``provenance_complete`` without any input is refused."""
        artifact = make_artifact(
            provenance_complete=True,
            source_ids=[],
            dataset_ids=[],
            transformation_ids=[],
        )

        with pytest.raises(ValidationError, match="provenance_complete"):
            artifact.validate()

    def test_traceable_artifact_validates(self) -> None:
        """An artifact derived from a source validates."""
        artifact = make_artifact()

        artifact.validate()

        assert artifact.source_ids

    def test_lineage_is_complete_only_with_an_input(self) -> None:
        """§24.2 — the lineage row must name what the artifact came from."""
        assert ArtifactLineage(
            artifact_lineage_id=ULID.new("VER_"),
            artifact_id=make_artifact().artifact_id,
        ).is_complete() is False
        assert ArtifactLineage(
            artifact_lineage_id=ULID.new("VER_"),
            artifact_id=make_artifact().artifact_id,
            source_ids=[ULID.new("SRC_")],
        ).is_complete() is True


class TestArtifactVersioning:
    """§18.1 — successive versions of the same artifact stay addressable."""

    def test_version_row_carries_its_artifact_and_semver(self) -> None:
        """A version row names its artifact and follows the §24.2 version format."""
        version = make_artifact_version(artifact_id=make_artifact().artifact_id)

        assert isinstance(version, ArtifactVersion)
        assert version.version == "1.0.0"
        assert version.artifact_id.startswith("ART_")

