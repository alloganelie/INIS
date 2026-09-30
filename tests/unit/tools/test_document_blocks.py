"""§21/§11 — ``extract_document_blocks`` locates every page and paragraph.

The ingestion can only attach a provable position to a §11 unit if the reader
states one. This module pins that statement: a PDF is cut **page by page**, a
DOCX **paragraph by paragraph** then table by table, a plain text payload by
paragraph, and every ``char_offset`` is checkable against the text the reader
returns — an offset nobody can verify would be a fabricated position (§0.2).

The fixtures are real documents (``tests/factories/file_factory.py``), not
plausible prefixes: what is asserted here is what ``pypdf``/``python-docx``
really read.
"""

from __future__ import annotations

import pytest

from app.core.errors import InfrastructureError, ValidationError
from app.tools.files.document_reader import (
    BLOCK_KINDS,
    extract_document_blocks,
    extract_document_text,
)
from tests.factories import docx_bytes, pdf_bytes

SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
PAGE_ONE = "Paris est la capitale de la France."
PAGE_TWO = "Berlin compte trois millions sept cent mille habitants."


def _assert_offsets_are_verifiable(path: str) -> list[dict]:
    """Return the blocks of *path* after checking their offsets really point."""
    _document, text = extract_document_text(path, source_id=SOURCE_ID)
    _document, blocks = extract_document_blocks(path, source_id=SOURCE_ID)

    for block in blocks:
        start = block["char_offset"]
        end = start + block["characters"]
        assert text[start:end] == block["text"]
        assert block["kind"] in BLOCK_KINDS
    return blocks


class TestPdfBlocks:
    """One block per page, numbered by the order of the document."""

    def test_each_page_is_its_own_block(self, tmp_path) -> None:
        path = tmp_path / "rapport.pdf"
        path.write_bytes(pdf_bytes([PAGE_ONE, PAGE_TWO]))

        blocks = _assert_offsets_are_verifiable(str(path))

        assert [block["kind"] for block in blocks] == ["page", "page"]
        assert [block["index"] for block in blocks] == [1, 2]
        assert [block["text"] for block in blocks] == [PAGE_ONE, PAGE_TWO]

    def test_a_page_without_text_keeps_its_number(self, tmp_path) -> None:
        """The reader never renumbers a document; the caller decides (§9.2)."""
        path = tmp_path / "scan.pdf"
        path.write_bytes(pdf_bytes([PAGE_ONE, ""]))

        blocks = _assert_offsets_are_verifiable(str(path))

        assert [(block["index"], block["text"]) for block in blocks] == [
            (1, PAGE_ONE),
            (2, ""),
        ]

    def test_a_corrupt_pdf_raises_instead_of_returning_nothing(self, tmp_path) -> None:
        path = tmp_path / "casse.pdf"
        path.write_bytes(b"%PDF-1.7\ntronque")

        with pytest.raises(InfrastructureError):
            extract_document_blocks(str(path), source_id=SOURCE_ID)

    def test_a_missing_file_is_a_validation_error(self, tmp_path) -> None:
        with pytest.raises(ValidationError):
            extract_document_blocks(str(tmp_path / "absent.pdf"), source_id=SOURCE_ID)


class TestDocxBlocks:
    """Paragraphs first (blank ones included), then one block per table."""

    def test_paragraphs_and_tables_are_separate_blocks(self, tmp_path) -> None:
        path = tmp_path / "note.docx"
        path.write_bytes(
            docx_bytes(
                ["Premier paragraphe.", "", "Second paragraphe."],
                tables=[[["clé", "valeur"], ["ville", "Paris"]]],
            )
        )

        blocks = _assert_offsets_are_verifiable(str(path))

        assert [block["kind"] for block in blocks] == [
            "paragraph",
            "paragraph",
            "paragraph",
            "table",
        ]
        assert [block["index"] for block in blocks] == [1, 2, 3, 1]
        assert blocks[3]["text"] == "clé\tvaleur\nville\tParis"

    def test_the_extracted_text_is_the_concatenation_of_the_blocks(self, tmp_path) -> None:
        """What the ingestion locates is what the reader returned, nothing else."""
        path = tmp_path / "note.docx"
        path.write_bytes(docx_bytes(["Un paragraphe.", "Un autre paragraphe."]))

        _document, text = extract_document_text(str(path), source_id=SOURCE_ID)
        _document, blocks = extract_document_blocks(str(path), source_id=SOURCE_ID)

        assert text == "\n".join(block["text"] for block in blocks)


class TestPlainTextBlocks:
    """A paragraph of prose is the smallest piece a text file can prove."""

    def test_paragraphs_are_located_in_the_file_text(self, tmp_path) -> None:
        path = tmp_path / "note.txt"
        path.write_text(
            "Premier paragraphe.\n\nSecond paragraphe.\n\n", encoding="utf-8"
        )

        blocks = _assert_offsets_are_verifiable(str(path))

        assert [block["kind"] for block in blocks] == ["section", "section"]
        assert [block["text"] for block in blocks] == [
            "Premier paragraphe.",
            "Second paragraphe.",
        ]

    def test_a_utf8_bom_is_not_document_text(self, tmp_path) -> None:
        path = tmp_path / "note.txt"
        path.write_bytes("\ufeffPremier paragraphe.".encode("utf-8"))

        blocks = _assert_offsets_are_verifiable(str(path))

        assert blocks[0]["text"] == "Premier paragraphe."
        assert blocks[0]["char_offset"] == 0

    def test_an_unsupported_suffix_is_refused_by_name(self, tmp_path) -> None:
        path = tmp_path / "archive.bin"
        path.write_bytes(b"\x00\x01\x02")

        with pytest.raises(InfrastructureError, match="unsupported document format"):
            extract_document_blocks(str(path), source_id=SOURCE_ID)
