"""§24.2 — the artifact record and its identifier sequence are what the spec says.

What these tests protect:

* the identifier is ``ART_{YYYY}_{SEQ6}`` (not a ULID — §0.3 does not cover it)
  and the yearly space cannot silently wrap;
* the record announces the digest and the size of the bytes that were generated;
* an upload failure degrades the delivery into a *stated* partial result (§25.2)
  instead of dropping the artifact or breaking the run.
"""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.artifacts.packager.artifact_packager import UNSTORED_REF_SCHEME, ArtifactPackager
from app.artifacts.packager.artifact_sequence import (
    ANNUAL_CAPACITY,
    InProcessArtifactSequence,
    artifact_year,
    format_artifact_id,
    parse_artifact_id,
)
from app.core.errors import ValidationError
from app.domain.entities.artifact import Artifact

ROWS = [{"information_id": "INF_1", "text": "Paris"}]


class FakeStorage:
    """Object-store double: records what it was asked to store."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.uploads: list[tuple[str, bytes, str | None]] = []
        self._fail_with = fail_with

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Record the upload, or raise the configured failure."""
        if self._fail_with is not None:
            raise self._fail_with
        self.uploads.append((key, data, content_type))
        return f"s3://inis-artifacts/{key}"


class TestArtifactSequence:
    """§24.2 — ``ART_{YYYY}_{SEQ6}``."""

    def test_format_and_parse_round_trip(self) -> None:
        identifier = format_artifact_id(2026, 42)

        assert identifier == "ART_2026_000042"
        assert parse_artifact_id(identifier) == (2026, 42)

    def test_malformed_identifier_is_not_parsed(self) -> None:
        """A ULID is not an artifact id: the §0.3 prefixes do not apply here."""
        assert parse_artifact_id("INF_01HZZ") is None
        assert parse_artifact_id("ART_2026_42") is None

    def test_yearly_space_does_not_wrap(self) -> None:
        """``000001`` cannot be handed out twice in the same year."""
        with pytest.raises(ValidationError, match="exhausted"):
            format_artifact_id(2026, ANNUAL_CAPACITY)
        with pytest.raises(ValidationError, match="exhausted"):
            format_artifact_id(2026, 0)

    def test_default_year_is_utc(self) -> None:
        assert artifact_year() >= 2026

    def test_in_process_sequence_hands_out_distinct_identifiers(self) -> None:
        sequence = InProcessArtifactSequence()

        identifiers = {sequence.next(2026) for _ in range(5)}

        assert len(identifiers) == 5
        assert sequence.next(2026) == "ART_2026_000006"

    def test_in_process_reset_is_for_test_isolation(self) -> None:
        sequence = InProcessArtifactSequence()
        sequence.next(2026)
        sequence.reset()

        assert sequence.next(2026) == "ART_2026_000001"


class TestArtifactPackager:
    """§24.2 — bytes → object storage → record."""

    def test_record_describes_the_bytes_that_were_stored(self) -> None:
        storage = FakeStorage()
        result = ArtifactPackager(storage).package(
            artifact_id="ART_2026_000001",
            output_format="csv",
            file_stem="REQ_1",
            purpose="Export demandé",
            rows=ROWS,
            source_ids=["SRC_1"],
        )

        key, content, content_type = storage.uploads[0]
        assert key == "deliveries/ART_2026_000001/REQ_1.csv"
        assert content_type == "text/csv"
        assert result.artifact.sha256 == hashlib.sha256(content).hexdigest()
        assert result.artifact.size_bytes == len(content)
        assert result.artifact.storage_ref == f"s3://inis-artifacts/{key}"
        assert result.limitation is None
        assert result.stored is True

    def test_format_drives_the_artifact_type(self) -> None:
        packager = ArtifactPackager(FakeStorage())

        export = packager.package(
            artifact_id="ART_2026_000001",
            output_format="xlsx",
            file_stem="REQ_1",
            purpose="Export",
            rows=ROWS,
            source_ids=["SRC_1"],
        )
        report = packager.package(
            artifact_id="ART_2026_000002",
            output_format="xml",
            file_stem="REQ_1",
            purpose="Rapport",
            payload={"request_id": "REQ_1"},
            source_ids=["SRC_1"],
        )

        assert export.artifact.artifact_type == "dataset_export"
        assert report.artifact.artifact_type == "report"

    def test_provenance_is_claimed_only_when_it_exists(self) -> None:
        """§24.2 — ``provenance_complete`` may not be claimed out of nothing."""
        without = ArtifactPackager(FakeStorage()).package(
            artifact_id="ART_2026_000003",
            output_format="json",
            file_stem="REQ_2",
            purpose="Sans source",
            payload={"request_id": "REQ_2"},
        )

        assert without.artifact.provenance_complete is False
        with pytest.raises(ValidationError):
            Artifact(**{**without.artifact.to_dict(), "provenance_complete": True}).validate()

    def test_unconfigured_storage_is_stated_not_hidden(self) -> None:
        """No object storage ⇒ the record exists and says the bytes are unreachable."""
        result = ArtifactPackager(None).package(
            artifact_id="ART_2026_000004",
            output_format="csv",
            file_stem="REQ_3",
            purpose="Export sans stockage",
            rows=ROWS,
            source_ids=["SRC_1"],
        )

        assert result.artifact.storage_ref.startswith(UNSTORED_REF_SCHEME)
        assert result.stored is False
        assert result.limitation and "non stocké" in result.limitation
        assert result.artifact.sha256  # the digest of the generated bytes is published

    def test_upload_failure_degrades_instead_of_crashing(self) -> None:
        """§25.2 — the delivery keeps its artifact, and names the failure."""
        storage = FakeStorage(fail_with=RuntimeError("bucket closed"))
        result = ArtifactPackager(storage).package(
            artifact_id="ART_2026_000005",
            output_format="csv",
            file_stem="REQ_4",
            purpose="Export",
            rows=ROWS,
            source_ids=["SRC_1"],
        )

        assert result.stored is False
        assert result.limitation and "bucket closed" in result.limitation

    def test_pdf_cannot_be_packaged(self) -> None:
        """§4.1 — no PDF writer in the V1 stack, so no PDF artifact either."""
        with pytest.raises(ValidationError, match="PDF"):
            ArtifactPackager(FakeStorage()).package(
                artifact_id="ART_2026_000006",
                output_format="pdf",
                file_stem="REQ_5",
                purpose="PDF demandé",
                payload={"request_id": "REQ_5"},
            )

    def test_a_record_with_a_bad_version_is_refused(self) -> None:
        """The §24.2 record is a domain entity: a bad semver is refused."""
        with pytest.raises(PydanticValidationError, match="semver"):
            ArtifactPackager(FakeStorage()).package(
                artifact_id="ART_2026_000007",
                output_format="csv",
                file_stem="REQ_6",
                purpose="Export",
                rows=ROWS,
                version="v1",
            )
