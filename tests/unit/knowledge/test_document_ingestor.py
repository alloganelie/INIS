"""§11/§24.3 — a document becomes units, each one locatable in its source.

The ingestion is where an uploaded file stops being an opaque blob: every unit it
produces must say *where* in the document it comes from (§11 traceability), and a
payload that cannot be read must produce **no** unit and one explicit limitation
instead of plausible-looking content (§0.2, §37).

Granularity is the point of the L2.6 lot: one unit per record (tabular), per
**page** (PDF), per **paragraph** and per **table** (DOCX), per paragraph (TXT),
and for an image one unit per embedded text tag plus one for its technical
properties — never an OCR, never a caption (§9.2).

No Docker, no network: the §21 readers run on a temporary copy of the bytes.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.connectors.images.image_connector import MIME_TYPES as IMAGE_MIME_BY_EXTENSION
from app.core.hashing import sha256_hex
from app.knowledge.ingestion.document_ingestor import IMAGE_SUFFIXES, ingest_document
from tests.factories import docx_bytes, pdf_bytes, png_bytes, workbook_bytes

DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/abc.csv"

CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
JSON_BYTES = json.dumps([{"city": "Paris"}, {"city": "Berlin"}]).encode("utf-8")
XML_BYTES = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<cities><city><name>Paris</name></city><city><name>Berlin</name></city></cities>"
)
TEXT_BYTES = b"Premier paragraphe.\n\nSecond paragraphe assez long pour une phrase.\n\n"
PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

PAGE_ONE = "Paris est la capitale de la France."
PAGE_TWO = "Berlin compte trois millions sept cent mille habitants."


async def _ingest(mime_type: str, data: bytes, *, file_name: str = "document.csv"):
    """Ingest *data* as *mime_type*, exactly as the upload endpoint does."""
    return await ingest_document(
        document_id=DOCUMENT_ID,
        source_id=SOURCE_ID,
        request_id=REQUEST_ID,
        file_name=file_name,
        mime_type=mime_type,
        data=data,
        storage_ref=STORAGE_REF,
    )


class TestTabularIngestion:
    """One unit per record, with the dataset it belongs to."""

    async def test_a_csv_yields_one_unit_per_row(self) -> None:
        outcome = await _ingest("text/csv", CSV_BYTES)

        assert len(outcome.units) == 2
        assert outcome.limitations == []

    async def test_each_unit_is_locatable(self) -> None:
        """§11 — a unit without a location is untraceable, hence not delivered."""
        units = (await _ingest("text/csv", CSV_BYTES)).units

        assert [unit["location"] for unit in units] == [
            {
                "kind": "row",
                "row": 1,
                "dataset_id": units[0]["dataset_id"],
                "columns": ["city", "population"],
            },
            {
                "kind": "row",
                "row": 2,
                "dataset_id": units[1]["dataset_id"],
                "columns": ["city", "population"],
            },
        ]
        for unit in units:
            assert unit["raw_reference"]["document_id"] == DOCUMENT_ID
            assert unit["raw_reference"]["location"] == unit["location"]
            assert unit["raw_reference"]["storage_ref"] == STORAGE_REF

    async def test_the_unit_keeps_the_record_and_a_readable_rendering(self) -> None:
        unit = (await _ingest("text/csv", CSV_BYTES)).units[0]

        assert unit["content"]["values"] == {"city": "Paris", "population": "2145906"}
        assert unit["content"]["text"] == "city=Paris; population=2145906"

    async def test_the_dataset_is_built_and_linked(self) -> None:
        outcome = await _ingest("text/csv", CSV_BYTES)

        dataset = outcome.dataset
        assert dataset is not None
        assert dataset["dataset_id"].startswith("DATA_")
        assert dataset["source_id"] == SOURCE_ID
        assert dataset["row_count"] == 2
        assert dataset["dataset_schema"] == {"city": "string", "population": "string"}


class TestWorkbookIngestion:
    """A workbook is read one sheet at a time, and the sheet is named (§11)."""

    async def test_a_workbook_is_read_sheet_by_sheet(self) -> None:
        data = workbook_bytes({"villes": [["city", "population"], ["Paris", 2145906]]})

        outcome = await _ingest(XLSX_MIME, data, file_name="cities.xlsx")

        assert len(outcome.units) == 1
        assert outcome.units[0]["content"]["values"] == {
            "city": "Paris",
            "population": 2145906,
        }
        # §11 — "row 1" is not a position until the sheet is named.
        assert outcome.units[0]["location"]["sheet"] == "villes"
        assert outcome.limitations == []

    async def test_the_sheets_that_were_not_read_are_named(self) -> None:
        """§0.2 — merging every sheet silently would invent a dataset."""
        data = workbook_bytes(
            {
                "villes": [["city", "population"], ["Paris", 2145906]],
                "annexe": [["note", "valeur"], ["x", 1]],
            }
        )

        outcome = await _ingest(XLSX_MIME, data, file_name="classeur.xlsx")

        assert len(outcome.units) == 1
        assert len(outcome.limitations) == 1
        assert "annexe" in outcome.limitations[0]
        assert "première feuille" in outcome.limitations[0]



class TestProseIngestion:
    """One unit per locatable block, with the sentences the block really holds."""

    async def test_a_text_file_yields_one_unit_per_section(self) -> None:
        outcome = await _ingest("text/plain", TEXT_BYTES, file_name="note.txt")

        assert [unit["content"]["text"] for unit in outcome.units] == [
            "Premier paragraphe.",
            "Second paragraphe assez long pour une phrase.",
        ]
        assert [unit["location"]["section"] for unit in outcome.units] == [1, 2]
        assert all(unit["type"] == "document_fragment" for unit in outcome.units)

    async def test_the_recorded_sentences_are_literal_substrings(self) -> None:
        """§1.2 — a fact is quoted from the document, never paraphrased."""
        outcome = await _ingest("text/plain", TEXT_BYTES, file_name="note.txt")

        for unit in outcome.units:
            for sentence in unit["content"].get("sentences", []):
                assert sentence in unit["content"]["text"]
        # The short paragraph is kept whole even though the splitter finds no
        # sentence in it: a fragment never loses text to its fact extraction.
        assert outcome.units[0]["content"] == {"text": "Premier paragraphe."}

    async def test_the_block_position_is_verifiable_in_the_extracted_text(self) -> None:
        """§11 — an offset nobody can check would be a fabricated position."""
        outcome = await _ingest("text/plain", TEXT_BYTES, file_name="note.txt")
        text = TEXT_BYTES.decode("utf-8")

        for unit in outcome.units:
            location = unit["location"]
            start = location["char_offset"]
            end = start + location["characters"]
            assert text[start:end] == unit["content"]["text"]

    async def test_prose_units_carry_no_dataset(self) -> None:
        outcome = await _ingest("text/plain", TEXT_BYTES, file_name="note.txt")

        assert outcome.dataset is None
        assert all(unit["dataset_id"] is None for unit in outcome.units)

    async def test_an_empty_text_yields_no_unit_and_says_why(self) -> None:
        outcome = await _ingest("text/plain", b"   \n\n  \n", file_name="vide.txt")

        assert outcome.units == []
        assert any("pas de texte lisible" in text for text in outcome.limitations)


class TestPdfIngestion:
    """§9.1 — a PDF is located page by page, never at an assumed position."""

    async def test_each_page_becomes_one_located_unit(self) -> None:
        outcome = await _ingest(
            PDF_MIME, pdf_bytes([PAGE_ONE, PAGE_TWO]), file_name="rapport.pdf"
        )

        assert [unit["location"]["kind"] for unit in outcome.units] == ["page", "page"]
        assert [unit["location"]["page"] for unit in outcome.units] == [1, 2]
        assert [unit["content"]["text"] for unit in outcome.units] == [PAGE_ONE, PAGE_TWO]
        assert outcome.units[0]["provenance"]["method"] == "app.tools.files.read_pdf"

    async def test_the_sentences_of_a_page_are_recorded_with_it(self) -> None:
        outcome = await _ingest(
            PDF_MIME, pdf_bytes([PAGE_ONE]), file_name="rapport.pdf"
        )

        # §21 — the sentences come from the fact extractor, verbatim.
        assert outcome.units[0]["content"]["sentences"] == [PAGE_ONE]

    async def test_a_page_without_a_text_layer_is_declared_not_invented(self) -> None:
        """§9.2 — no OCR: a scanned page is a gap, not a description."""
        outcome = await _ingest(
            PDF_MIME, pdf_bytes([PAGE_ONE, ""]), file_name="scan.pdf"
        )

        assert [unit["location"]["page"] for unit in outcome.units] == [1]
        assert any("couche texte" in text for text in outcome.limitations)
        assert any("OCR" in text for text in outcome.limitations)

    async def test_the_granularity_that_was_used_is_stated(self) -> None:
        outcome = await _ingest(PDF_MIME, pdf_bytes([PAGE_ONE]), file_name="r.pdf")

        assert any(
            "localisées par page" in text for text in outcome.limitations
        ), outcome.limitations




class TestDocxIngestion:
    """§9.1 — a DOCX is located paragraph by paragraph, tables included."""

    async def test_paragraphs_and_tables_keep_their_own_index(self) -> None:
        data = docx_bytes(
            [
                "Le premier paragraphe explique la méthode.",
                "",
                "Le second donne le résultat final.",
            ],
            tables=[[["clé", "valeur"], ["ville", "Paris"]]],
        )

        outcome = await _ingest(DOCX_MIME, data, file_name="note.docx")

        first = "Le premier paragraphe explique la méthode."
        second = "Le second donne le résultat final."
        table = "clé\tvaleur\nville\tParis"

        assert [unit["location"]["kind"] for unit in outcome.units] == [
            "paragraph",
            "paragraph",
            "table",
        ]
        assert [unit["location"]["paragraph"] for unit in outcome.units[:2]] == [1, 3]
        assert outcome.units[2]["location"]["table"] == 1
        # §11 — every offset is verifiable in the extracted text: the blocks are
        # joined by the reader's separator, and the blank paragraph keeps its
        # rank instead of being silently dropped.
        extracted = f"{first}\n\n{second}\n{table}"
        for unit in outcome.units:
            start = unit["location"]["char_offset"]
            end = start + unit["location"]["characters"]
            assert extracted[start:end] == unit["content"]["text"]
        assert all(unit["type"] == "document_fragment" for unit in outcome.units)

    async def test_the_table_cells_are_kept_verbatim(self) -> None:
        data = docx_bytes(["Un paragraphe."], tables=[[["clé", "valeur"]]])

        outcome = await _ingest(DOCX_MIME, data, file_name="table.docx")

        assert outcome.units[-1]["content"]["text"] == "clé\tvaleur"

    async def test_the_paragraph_granularity_is_stated(self) -> None:
        data = docx_bytes(["Un paragraphe assez long pour être une phrase complète."])

        outcome = await _ingest(DOCX_MIME, data, file_name="note.docx")

        assert any("localisées par paragraphe" in text for text in outcome.limitations)


class TestImageIngestion:
    """§9.1/§9.2 — what an image really carries, and nothing more."""

    pytest.importorskip("PIL.Image", reason="Pillow optional (§4.1, D6)")

    async def test_an_embedded_tag_and_the_properties_become_units(self) -> None:
        outcome = await _ingest(
            "image/png", png_bytes("Titre du rapport"), file_name="figure.png"
        )

        assert [unit["type"] for unit in outcome.units] == [
            "image_region",
            "image_region",
        ]
        assert outcome.units[0]["content"]["text"] == "Titre du rapport"
        assert outcome.units[0]["location"] == {
            "tag": "ImageDescription",
            "kind": "embedded_text",
        }
        properties = outcome.units[1]["content"]
        assert (properties["width"], properties["height"]) == (8, 6)
        assert properties["format"] == "PNG"

    async def test_the_units_point_at_the_stored_object(self) -> None:
        """§18.1 — the temporary copy the tool read is already gone."""
        outcome = await _ingest("image/png", png_bytes(), file_name="photo.png")

        for unit in outcome.units:
            assert unit["provenance"]["extracted_from"] == STORAGE_REF
            assert unit["raw_reference"]["storage_ref"] == STORAGE_REF
            assert unit["raw_reference"]["file_name"] == "photo.png"
            assert "file://" not in json.dumps(unit)
            assert unit["document_id"] == DOCUMENT_ID
            assert unit["context"] == {
                "request_id": REQUEST_ID,
                "origin": "uploaded_image",
            }
            assert unit["versions"] == [unit["information_id"]]

    async def test_an_image_without_text_yields_its_properties_only(self) -> None:
        """§1.2 — no OCR, no caption: no textual unit is invented."""
        outcome = await _ingest("image/png", png_bytes(), file_name="photo.png")

        assert len(outcome.units) == 1
        assert outcome.units[0]["location"] == {"kind": "image_properties"}
        assert any("ni OCR ni légende" in text for text in outcome.limitations)

    async def test_an_undecodable_image_names_the_cause(self) -> None:
        outcome = await _ingest(
            "image/png", b"\x89PNG\r\n\x1a\npas une vraie image", file_name="casse.png"
        )

        assert outcome.units == []
        assert len(outcome.limitations) == 1
        assert "Aucune unité extraite" in outcome.limitations[0]
        assert "pillow_available=False" in outcome.limitations[0]

    async def test_the_image_types_are_the_ones_the_connector_reads(self) -> None:
        """An image type INIS claims to ingest but cannot decode would be a lie."""
        assert set(IMAGE_SUFFIXES) == set(IMAGE_MIME_BY_EXTENSION.values())


class TestUnreadablePayloads:
    """§0.2/§37 — no unit is invented when the content cannot be read."""

    async def test_a_corrupt_pdf_yields_no_unit_and_names_the_cause(self) -> None:
        outcome = await _ingest(PDF_MIME, b"%PDF-1.7\ntronque", file_name="casse.pdf")

        assert outcome.units == []
        assert len(outcome.limitations) == 1
        assert "Aucune unité extraite" in outcome.limitations[0]

    async def test_a_corrupt_json_yields_no_unit(self) -> None:
        outcome = await _ingest(
            "application/json", b"{ceci n est pas du json", file_name="x.json"
        )

        assert outcome.units == []
        assert "Aucune unité extraite" in outcome.limitations[0]

    async def test_an_empty_csv_yields_no_unit(self) -> None:
        outcome = await _ingest("text/csv", b"city,population\n", file_name="vide.csv")

        assert outcome.units == []
        assert any("aucun enregistrement" in text for text in outcome.limitations)

    async def test_a_type_without_a_reader_is_refused_by_name(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data/whatever.txt", "x")

        outcome = await _ingest(
            "application/zip", buffer.getvalue(), file_name="archive.zip"
        )

        assert outcome.units == []
        assert "application/zip" in outcome.limitations[0]




class TestUnitContract:
    """Every produced unit satisfies §11, or it is not produced at all."""

    async def test_units_are_validated_by_the_domain_entity(self) -> None:
        outcome = await _ingest("text/csv", CSV_BYTES)

        for unit in outcome.units:
            assert unit["information_id"].startswith("INF_")
            assert unit["type"] in {"record", "document_fragment", "image_region"}
            # §12 — the reader that produced this unit *is* the normalisation
            # step: a located §11 unit is never the untouched material.
            assert unit["data_stage"] == "normalized"
            assert unit["provenance"]["method"] == "app.tools.files.read_csv"
            assert unit["provenance"]["extracted_from"] == STORAGE_REF
            assert unit["versions"] == [unit["information_id"]]
            # §15 — no confidence score is invented, and the nature is stated.
            assert unit["confidence"] == {"score": None, "not_a_probability": True}
            assert unit["language"] is None

    async def test_the_ingestion_does_not_touch_the_bytes_it_reads(self) -> None:
        """The hash of the delivered document is the hash of what was stored."""
        digest = sha256_hex(CSV_BYTES)

        await _ingest("text/csv", CSV_BYTES)

        assert sha256_hex(CSV_BYTES) == digest

    async def test_an_empty_zip_workbook_is_not_a_dataset(self) -> None:
        """A ZIP that is not a workbook must not become a plausible dataset."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data/whatever.txt", "x")

        outcome = await _ingest(XLSX_MIME, buffer.getvalue(), file_name="faux.xlsx")

        assert outcome.units == []
        assert "Aucune unité extraite" in outcome.limitations[0]

    async def test_json_and_xml_still_become_records(self) -> None:
        for mime_type, payload, file_name in (
            ("application/json", JSON_BYTES, "villes.json"),
            ("application/xml", XML_BYTES, "villes.xml"),
        ):
            outcome = await _ingest(mime_type, payload, file_name=file_name)

            assert len(outcome.units) == 2, mime_type
            assert all(
                unit["location"]["kind"] == "row" for unit in outcome.units
            ), mime_type
