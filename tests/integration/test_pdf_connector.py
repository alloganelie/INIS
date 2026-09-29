"""§9.1 — the PDF connector on real PDF files.

The connector is the only route by which a PDF becomes an INIS source: it must
find the file, read its bytes, and report honest structure (page count, metadata,
text volume, tables) instead of guessing. The tests build real PDFs with
``pypdf`` in a temporary directory — no fixture blobs, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pypdf

from app.connectors.base import Query, RawSource, SourceCandidate
from app.connectors.files.pdf_connector import CONTENT_TYPE, PDFConnector

pytestmark = pytest.mark.asyncio


def _write_pdf(path: Path, pages: int = 1) -> Path:
    """Write a real, readable PDF with *pages* blank pages."""
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@pytest.fixture
def pdf_dir(tmp_path: Path) -> Path:
    """Return a directory holding two real PDFs."""
    _write_pdf(tmp_path / "rapport_inflation.pdf", pages=2)
    _write_pdf(tmp_path / "annexe_chomage.pdf", pages=1)
    return tmp_path


class TestDiscovery:
    """§9.1 — the connector finds the documents the query names."""

    async def test_only_matching_files_are_discovered(self, pdf_dir: Path) -> None:
        """Discovery filters on the file name and returns candidates."""
        connector = PDFConnector(str(pdf_dir))

        candidates = await connector.discover(Query(query_string="inflation"))

        assert [candidate.source_id for candidate in candidates] == ["pdf-rapport_inflation"]
        assert candidates[0].metadata["filename"] == "rapport_inflation.pdf"

    async def test_no_match_yields_no_candidate(self, pdf_dir: Path) -> None:
        """A query that matches nothing returns an empty list, not a fallback."""
        connector = PDFConnector(str(pdf_dir))

        assert await connector.discover(Query(query_string="sans-rapport")) == []


class TestRetrieval:
    """§9.1 — the raw bytes and their identity are preserved."""

    async def test_retrieve_returns_the_file_bytes(self, pdf_dir: Path) -> None:
        """The retrieved payload is exactly the file on disk."""
        connector = PDFConnector(str(pdf_dir))
        candidate = (await connector.discover(Query(query_string="annexe")))[0]

        raw = await connector.retrieve(candidate)

        assert isinstance(raw, RawSource)
        assert raw.content_type == CONTENT_TYPE
        assert raw.data == (pdf_dir / "annexe_chomage.pdf").read_bytes()


class TestInspection:
    """§9.1 — the reported structure is measured, never assumed."""

    async def test_page_count_is_reported(self, pdf_dir: Path) -> None:
        """``record_count`` is the real page count of the document."""
        connector = PDFConnector(str(pdf_dir))
        candidate = (await connector.discover(Query(query_string="inflation")))[0]

        metadata = await connector.inspect(await connector.retrieve(candidate))

        assert metadata.record_count == 2
        assert metadata.schema is not None
        assert metadata.schema["pages"] == "2"
        assert metadata.schema["encrypted"] == "False"
        assert metadata.size_bytes > 0

    async def test_a_corrupt_file_is_reported_as_empty_not_crashed(
        self, tmp_path: Path
    ) -> None:
        """A file that is not a PDF degrades gracefully (§25.1)."""
        connector = PDFConnector(str(tmp_path))
        raw = RawSource(
            source_id="pdf-corrupt",
            data=b"not a pdf at all",
            content_type=CONTENT_TYPE,
            metadata={},
        )

        metadata = await connector.inspect(raw)

        assert metadata.record_count == 0
        assert metadata.size_bytes == len(b"not a pdf at all")

    async def test_unreadable_file_surfaces_the_underlying_error(self, tmp_path: Path) -> None:
        """Retrieving a missing path fails loudly instead of returning bytes."""
        connector = PDFConnector(str(tmp_path))
        candidate = SourceCandidate(
            source_id="pdf-ghost",
            location=str(tmp_path / "ghost.pdf"),
            metadata={},
        )

        with pytest.raises(FileNotFoundError):
            await connector.retrieve(candidate)


class TestConnectorContract:
    """§9 — every connector exposes the same health and identity surface."""

    async def test_health_reports_the_available_parsers(self) -> None:
        """``pypdf`` is a required dependency: health is honest about it."""
        health = await PDFConnector().health_check()

        assert health.healthy is True
        assert "PDF connector healthy" in health.message

    async def test_metadata_declares_the_supported_types(self) -> None:
        """The connector advertises the source types it can read."""
        metadata = await PDFConnector().metadata()

        assert metadata.connector_id == "pdf-connector"
        assert metadata.supported_source_types == ["pdf"]

