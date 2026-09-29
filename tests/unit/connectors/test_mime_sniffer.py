"""§9.1/§36.6 — a document is identified by its bytes, never by its name.

The upload endpoint is the only place where a client can hand INIS arbitrary
bytes; a permissive detector there would let a ZIP archive enter the pipeline as
a "CSV" and fail much later, or let a crafted name escape the storage prefix.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from app.connectors.files.mime_sniffer import (
    SUPPORTED_MIME_TYPES,
    require_supported,
    sniff_mime_type,
)
from app.core.errors import ValidationError

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
JSON_BYTES = json.dumps({"city": "Paris", "population": 2145906}).encode("utf-8")
XML_BYTES = b"<?xml version='1.0' encoding='UTF-8'?><cities><city>Paris</city></cities>"
MD_BYTES = b"# Rapport\n\n- Paris\n- Berlin\n"


def _ooxml(member: str) -> bytes:
    """Return a minimal ZIP archive that contains *member*."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(member, "<xml/>")
    return buffer.getvalue()


class TestDetectionByContent:
    """What the bytes prove wins over what the client sent."""

    def test_pdf_is_detected_by_its_signature(self) -> None:
        sniffed = sniff_mime_type(PDF_BYTES, "rapport.csv")

        assert sniffed.mime_type == "application/pdf"
        assert sniffed.supported is True
        assert "PDF" in sniffed.evidence

    def test_xlsx_is_detected_inside_the_zip_archive(self) -> None:
        sniffed = sniff_mime_type(_ooxml("xl/workbook.xml"), "donnees.txt")

        assert sniffed.mime_type.endswith("spreadsheetml.sheet")
        assert sniffed.extension == ".xlsx"
        assert "xl/workbook.xml" in sniffed.evidence

    def test_docx_is_detected_inside_the_zip_archive(self) -> None:
        sniffed = sniff_mime_type(_ooxml("word/document.xml"), "note.docx")

        assert sniffed.mime_type.endswith("wordprocessingml.document")
        assert sniffed.extension == ".docx"

    def test_a_plain_zip_is_not_taken_for_a_workbook(self) -> None:
        """The Office Open XML member proves the type, not the ZIP header."""
        sniffed = sniff_mime_type(_ooxml("data/whatever.txt"))

        assert sniffed.mime_type == "application/zip"
        assert sniffed.supported is False

    def test_csv_is_detected_by_its_tabular_structure(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES, "cities.txt")

        assert sniffed.mime_type == "text/csv"
        assert sniffed.extension == ".csv"

    def test_json_is_detected_by_parsing_it(self) -> None:
        assert sniff_mime_type(JSON_BYTES).mime_type == "application/json"

    def test_xml_is_detected_by_parsing_it(self) -> None:
        assert sniff_mime_type(XML_BYTES).mime_type == "application/xml"

    def test_prose_is_not_mistaken_for_a_table(self) -> None:
        """One column of sentences is text, not CSV."""
        prose = b"Bonjour.\nCeci est un paragraphe.\nEt une autre phrase.\n"

        assert sniff_mime_type(prose).mime_type == "text/plain"

    def test_markdown_needs_the_client_hint(self) -> None:
        assert sniff_mime_type(MD_BYTES, "notes.md").mime_type == "text/markdown"
        assert sniff_mime_type(MD_BYTES, "notes.txt").mime_type == "text/plain"

    def test_binary_without_signature_is_not_text(self) -> None:
        sniffed = sniff_mime_type(b"\x00\x01\x02\x03binary\x00")

        assert sniffed.mime_type == "application/octet-stream"
        assert sniffed.supported is False

    def test_the_whitelist_is_the_spec_one(self) -> None:
        assert SUPPORTED_MIME_TYPES == {
            "text/csv",
            "application/json",
            "application/xml",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        }


class TestRefusal:
    """An unsupported type is refused *with its detected type named* (§25.2)."""

    def test_image_is_refused_as_an_image(self) -> None:
        with pytest.raises(ValidationError) as failure:
            require_supported(b"\x89PNG\r\n\x1a\nrest", "photo.csv")

        assert "image/png" in str(failure.value)
        assert "Types acceptés" in str(failure.value)

    def test_archive_is_refused_as_an_archive(self) -> None:
        with pytest.raises(ValidationError, match="archive ZIP"):
            require_supported(_ooxml("data/whatever.txt"), "archive.zip")

    def test_supported_types_pass(self) -> None:
        assert require_supported(CSV_BYTES, "cities.csv").mime_type == "text/csv"


class TestSafeFileName:
    """The stored name describes the bytes and cannot escape its prefix (§18.1)."""

    def test_directory_components_are_stripped(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES)

        assert sniffed.safe_file_name("../../etc/passwd.csv", fallback_stem="DOC_1") == (
            "passwd.csv"
        )

    def test_windows_separators_are_stripped(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES)

        assert (
            sniffed.safe_file_name(r"C:\temp\cities.csv", fallback_stem="DOC_1")
            == "cities.csv"
        )

    def test_the_detected_extension_wins_over_the_client_one(self) -> None:
        """A PDF named ``.csv`` is stored as a PDF, never as a CSV."""
        sniffed = sniff_mime_type(PDF_BYTES, "rapport.csv")

        assert sniffed.safe_file_name("rapport.csv", fallback_stem="DOC_1") == "rapport.pdf"

    def test_an_empty_name_falls_back_to_the_document_id(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES)

        assert sniffed.safe_file_name("", fallback_stem="DOC_1") == "DOC_1.csv"
        assert sniffed.safe_file_name("..", fallback_stem="DOC_1") == "DOC_1.csv"
