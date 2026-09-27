"""Tests for the Pillow-backed image connector per §9.1 and §1.1.

Pillow is an optional dependency (decision D6), so the module is skipped
when it is unavailable instead of failing the suite — but *every* test that
runs asserts real behaviour, including the explicit degradation path.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.connectors.base import Query, RawSource
from app.connectors.images.image_connector import (
    IMAGE_EXTENSIONS,
    ImageConnector,
    _pillow,
    read_image_metadata,
)

pytest.importorskip("PIL.Image", reason="Pillow optional (§4.1, D6)")


def _png_bytes(
    *,
    size: tuple[int, int] = (4, 3),
    text: str | None = None,
    mode: str = "RGB",
) -> bytes:
    """Build a deterministic in-memory PNG, optionally carrying a tEXt chunk."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    image = Image.new(mode, size, color=(10, 20, 30))
    buffer = io.BytesIO()
    if text is None:
        image.save(buffer, format="PNG")
    else:
        info = PngInfo()
        info.add_text("ImageDescription", text)
        image.save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


class TestReadImageMetadata:
    """Unit tests for the raw-bytes metadata reader."""

    def test_reads_format_mode_and_dimensions(self) -> None:
        metadata = read_image_metadata(_png_bytes(size=(7, 5)))

        assert metadata.pillow_available is True
        assert metadata.format == "PNG"
        assert metadata.mode == "RGB"
        assert (metadata.width, metadata.height) == (7, 5)
        assert metadata.pixel_count == 35
        assert metadata.frames == 1

    def test_reads_literal_text_chunk(self) -> None:
        metadata = read_image_metadata(_png_bytes(text="Titre du rapport"))

        assert metadata.text_source == "Titre du rapport"
        assert metadata.to_schema()["text:ImageDescription"] == "Titre du rapport"

    def test_no_text_chunk_yields_no_text_source(self) -> None:
        """No OCR, no captioning: absence of text MUST stay ``None`` (§1.2)."""
        metadata = read_image_metadata(_png_bytes())

        assert metadata.text_source is None
        assert metadata.textual_tags == {}

    def test_transparency_is_reported(self) -> None:
        metadata = read_image_metadata(_png_bytes(mode="RGBA"))

        assert metadata.has_transparency is True

    def test_schema_values_are_strings(self) -> None:
        schema = read_image_metadata(_png_bytes(size=(2, 2))).to_schema()

        assert all(
            isinstance(key, str) and isinstance(value, str) for key, value in schema.items()
        )

    def test_corrupt_payload_raises(self) -> None:
        with pytest.raises(Exception):
            read_image_metadata(b"not-an-image")


class TestImageConnector:
    """End-to-end connector behaviour on a temporary directory."""

    async def test_discover_filters_by_query(self, tmp_path: Path) -> None:
        (tmp_path / "chart_2026.png").write_bytes(_png_bytes())
        (tmp_path / "logo.png").write_bytes(_png_bytes())

        connector = ImageConnector(base_path=str(tmp_path))
        candidates = await connector.discover(Query(query_string="chart"))

        assert [candidate.source_id for candidate in candidates] == ["image-chart_2026"]
        assert candidates[0].metadata["media_type"] == "image/png"

    async def test_discover_covers_all_supported_extensions(self, tmp_path: Path) -> None:
        for extension in IMAGE_EXTENSIONS:
            (tmp_path / f"sample.{extension}").write_bytes(_png_bytes())

        connector = ImageConnector(base_path=str(tmp_path))
        candidates = await connector.discover(Query(query_string="sample"))

        assert len(candidates) == len(IMAGE_EXTENSIONS)

    async def test_retrieve_returns_bytes_and_mime(self, tmp_path: Path) -> None:
        payload = _png_bytes()
        (tmp_path / "photo.jpg").write_bytes(payload)

        connector = ImageConnector(base_path=str(tmp_path))
        candidates = await connector.discover(Query(query_string="photo"))
        raw = await connector.retrieve(candidates[0])

        assert isinstance(raw.data, bytes)
        assert raw.data == payload
        assert raw.content_type == "image/jpeg"

    async def test_inspect_exposes_technical_schema(self, tmp_path: Path) -> None:
        (tmp_path / "figure.png").write_bytes(_png_bytes(size=(9, 4), text="Annexe A"))

        connector = ImageConnector(base_path=str(tmp_path))
        candidates = await connector.discover(Query(query_string="figure"))
        raw = await connector.retrieve(candidates[0])
        metadata = await connector.inspect(raw)

        assert metadata.record_count == 1
        assert metadata.size_bytes == len(raw.data)
        assert metadata.schema is not None
        assert metadata.schema["format"] == "PNG"
        assert metadata.schema["width"] == "9"
        assert metadata.schema["text:ImageDescription"] == "Annexe A"

    async def test_inspect_of_non_image_degrades_without_raising(self) -> None:
        connector = ImageConnector(base_path=".")
        raw = RawSource(
            source_id="image-broken",
            data=b"\x00\x01\x02",
            content_type="image/png",
            metadata={"filename": "broken.png"},
        )

        metadata = await connector.inspect(raw)

        assert metadata.size_bytes == 3
        assert metadata.record_count == 0
        # Degradation is explicit, never silent (§0.2).
        assert metadata.schema is not None
        assert metadata.schema["format"] == "unknown"
        assert "decode_error" in metadata.schema

    async def test_health_check_reports_pillow_availability(self) -> None:
        connector = ImageConnector(base_path=".")

        status = await connector.health_check()

        assert status.healthy is (_pillow() is not None)
        assert "Pillow" in status.message

    async def test_metadata_declares_v2_and_extensions(self) -> None:
        connector = ImageConnector(base_path=".")

        metadata = await connector.metadata()

        assert metadata.connector_id == "image-connector"
        assert metadata.version == "2.0.0"
        assert set(metadata.supported_source_types) == set(IMAGE_EXTENSIONS)
