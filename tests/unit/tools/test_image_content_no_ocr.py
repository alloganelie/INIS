"""§21/§9.2 — an image is quoted, never described: there is no OCR in V1.

``extract_image_content(path)`` is the §21 tool the ingestion branches on for an
uploaded image. Two things must stay true, and this module is what holds them:

* every ``image_region`` unit comes from a string **literally stored in the
  file** (EXIF ``ImageDescription``, PNG ``tEXt``…) or from the image's own
  technical properties — no caption, no semantic label, nothing guessed (§1.2);
* when Pillow is absent (optional dependency, decision D6) the connector reports
  ``pillow_available=False`` and the tool **refuses** instead of returning an
  empty, plausible-looking result (§25.1).

The Pillow-absent case is simulated by replacing the module's Pillow resolver, so
the contract is verified on a machine where the optional dependency *is*
installed — the case that would otherwise never be exercised.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.connectors.base import RawSource
from app.connectors.images import image_connector
from app.connectors.images.image_connector import ImageConnector, read_image_metadata
from app.core.errors import InfrastructureError, ValidationError
from app.tools.images.image_analyzer import extract_image_content
from tests.factories import png_bytes

SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
TRANSFORMATION_ID = "TRF_01M3Q0000000000000000000AA"

TAG_TEXT = "Titre du rapport annuel"

pytest.importorskip("PIL.Image", reason="Pillow optional (§4.1, D6)")


@pytest.fixture
def tagged_image(tmp_path: Path) -> str:
    """Write a PNG carrying one literal ``ImageDescription`` tag."""
    path = tmp_path / "figure.png"
    path.write_bytes(png_bytes(TAG_TEXT))
    return str(path)


@pytest.fixture
def untagged_image(tmp_path: Path) -> str:
    """Write a PNG that carries no text at all."""
    path = tmp_path / "photo.png"
    path.write_bytes(png_bytes())
    return str(path)


class TestExtractedContent:
    """What an image really carries, unit by unit."""

    @pytest.mark.asyncio
    async def test_an_embedded_tag_becomes_a_literal_text_unit(
        self, tagged_image: str
    ) -> None:
        units = await extract_image_content(
            tagged_image,
            source_id=SOURCE_ID,
            document_id=DOCUMENT_ID,
            transformation_id=TRANSFORMATION_ID,
        )

        text_units = [u for u in units if u.location["kind"] == "embedded_text"]
        assert len(text_units) == 1
        assert text_units[0].content["text"] == TAG_TEXT
        assert text_units[0].type == "image_region"
        # §12 — what was read out of the file is a derived value, and it says by
        # which transformation it was obtained.
        assert text_units[0].data_stage == "derived"
        assert text_units[0].provenance["method"] == "image_analyzer"
        assert text_units[0].provenance["transformation_id"] == TRANSFORMATION_ID

    @pytest.mark.asyncio
    async def test_the_technical_properties_are_one_unit(self, tagged_image: str) -> None:
        units = await extract_image_content(
            tagged_image, source_id=SOURCE_ID, document_id=DOCUMENT_ID
        )

        properties = [u for u in units if u.location["kind"] == "image_properties"]
        assert len(properties) == 1
        assert properties[0].content["format"] == "PNG"
        assert (properties[0].content["width"], properties[0].content["height"]) == (
            8,
            6,
        )

    @pytest.mark.asyncio
    async def test_an_image_without_text_yields_no_textual_unit(
        self, untagged_image: str
    ) -> None:
        """§9.2 — no OCR: absence of text MUST stay an absence."""
        units = await extract_image_content(untagged_image, source_id=SOURCE_ID)

        assert [unit.location["kind"] for unit in units] == ["image_properties"]
        assert all("text" not in unit.content for unit in units)

    @pytest.mark.asyncio
    async def test_a_unit_without_provenance_is_refused(self, tagged_image: str) -> None:
        """§0.2 — a factual unit MUST reference the source it came from."""
        with pytest.raises(ValidationError):
            await extract_image_content(tagged_image, source_id="")

    @pytest.mark.asyncio
    async def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError):
            await extract_image_content(str(tmp_path / "absent.png"), source_id=SOURCE_ID)



class TestWithoutPillow:
    """Decision D6 — the degradation is stated, never simulated."""

    @pytest.fixture(autouse=True)
    def _no_pillow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make the connector behave as it does in a Pillow-less deployment."""
        monkeypatch.setattr(image_connector, "_pillow", lambda: None)

    def test_the_metadata_reports_pillow_available_false(self, tagged_image: str) -> None:
        metadata = read_image_metadata(Path(tagged_image).read_bytes())

        assert metadata.pillow_available is False
        assert metadata.width == 0 and metadata.height == 0
        assert metadata.textual_tags == {}
        assert metadata.to_schema()["pillow_available"] == "False"

    @pytest.mark.asyncio
    async def test_the_tool_refuses_instead_of_returning_nothing(
        self, tagged_image: str
    ) -> None:
        """§25.1 — an unreadable image is not an empty image."""
        with pytest.raises(InfrastructureError, match="Pillow"):
            await extract_image_content(tagged_image, source_id=SOURCE_ID)

    @pytest.mark.asyncio
    async def test_the_connector_health_check_names_the_degradation(self) -> None:
        health = await ImageConnector().health_check()

        assert health.healthy is False
        assert "Pillow" in health.message

    @pytest.mark.asyncio
    async def test_inspect_degrades_to_a_size_only_schema(self) -> None:
        """The connector keeps discovering bytes; it stops describing them."""
        raw = RawSource(
            source_id="image-figure",
            data=png_bytes("Titre"),
            content_type="image/png",
            metadata={},
        )

        metadata = await ImageConnector().inspect(raw)

        assert metadata.schema["format"] == "unknown"
        assert metadata.schema["pillow_available"] == "False"

    @pytest.mark.asyncio
    async def test_a_payload_that_cannot_be_decoded_stays_marked_as_such(self) -> None:
        raw = RawSource(
            source_id="image-casse",
            data=b"pas une image",
            content_type="image/png",
            metadata={},
        )

        metadata = await ImageConnector().inspect(raw)

        # No Pillow *and* unusable bytes: the schema carries both facts (§0.2).
        assert metadata.schema["format"] == "unknown"
        assert metadata.schema["pillow_available"] == "False"
        assert metadata.size_bytes == len(b"pas une image")



class TestNoHiddenVision:
    """There is no model call behind an image: only the file is read."""

    @pytest.mark.asyncio
    async def test_no_llm_is_involved_in_image_extraction(
        self, tagged_image: str, mock_llm
    ) -> None:
        await extract_image_content(tagged_image, source_id=SOURCE_ID)

        assert mock_llm.calls == []

