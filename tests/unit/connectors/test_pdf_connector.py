"""Tests for PDFConnector per §9.1 (tmp_path, pypdf fixtures)."""

from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.pdf_connector import PDFConnector


def _minimal_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF with extractable text (offsets computed)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 24 Tf 100 700 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_at)
    )
    return bytes(out)


def _blank_pdf(path: Path, pages: int = 2) -> None:
    """Write a multi-page (blank) PDF via pypdf."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as f:
        writer.write(f)


@pytest.mark.asyncio
async def test_pdf_discover(tmp_path: Path) -> None:
    """PDF files matching the query are discovered."""
    _blank_pdf(tmp_path / "report_test.pdf")

    candidates = await PDFConnector(base_path=str(tmp_path)).discover(
        Query(query_string="report")
    )

    assert len(candidates) == 1
    assert candidates[0].source_id == "pdf-report_test"


@pytest.mark.asyncio
async def test_pdf_retrieve(tmp_path: Path) -> None:
    """Raw PDF bytes are retrieved with the PDF content type."""
    _blank_pdf(tmp_path / "report_test.pdf")
    connector = PDFConnector(base_path=str(tmp_path))

    candidates = await connector.discover(Query(query_string="report"))
    raw = await connector.retrieve(candidates[0])

    assert raw.content_type == "application/pdf"
    assert isinstance(raw.data, bytes)
    assert raw.data[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_pdf_inspect(tmp_path: Path) -> None:
    """Inspect reports page count, text chars and tables wiring."""
    text_path = tmp_path / "hello_test.pdf"
    text_path.write_bytes(_minimal_pdf("Hello PDF"))
    _blank_pdf(tmp_path / "blank_test.pdf")
    connector = PDFConnector(base_path=str(tmp_path))

    text_raw = await connector.retrieve(
        (await connector.discover(Query(query_string="hello")))[0]
    )
    text_meta = await connector.inspect(text_raw)
    assert text_meta.record_count == 1
    assert text_meta.schema is not None
    assert text_meta.schema["pages"] == "1"
    assert int(text_meta.schema["text_chars"]) > 0

    blank_raw = await connector.retrieve(
        (await connector.discover(Query(query_string="blank")))[0]
    )
    blank_meta = await connector.inspect(blank_raw)
    assert blank_meta.record_count == 2
