"""§11/§24.3 — a document becomes units, each one locatable in its source.

The ingestion is where an uploaded file stops being an opaque blob: every unit it
produces must say *where* in the document it comes from (#§11 traceability), and
a payload that cannot be read must produce **no** unit and one explicit
limitation instead of plausible-looking content (§0.2, §37).

No Docker, no network: the §21 readers run on a temporary copy of the bytes.
"""

from __future__ import annotations

import io
import json
import zipfile

from app.core.hashing import sha256_hex
from app.knowledge.ingestion.document_ingestor import ingest_document

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
TEXT_BYTES = b"Premier paragraphe.\n\nSecond paragraphe.\n\n"


def _ingest(mime_type: str, data: bytes, *, file_name: str = "document.csv"):
    """Ingest *data* as *mime_type*."""
    return ingest_document(
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

    def test_a_csv_yields_one_unit_per_row(self) -> None:
        outcome = _ingest("text/csv", CSV_BYTES)

        assert len(outcome.units) == 2
        assert outcome.limitations == []

    def test_each_unit_is_locatable(self) -> None:
        """§11 — a unit without a location is untraceable, hence not delivered."""
        units = _ingest("text/csv", CSV_BYTES).units

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

    def test_the_unit_keeps_the_record_and_a_readable_rendering(self) -> None:
        unit = _ingest("text/csv", CSV_BYTES).units[0]

        assert unit["content"]["values"] == {"city": "Paris", "population": "2145906"}
        assert unit["content"]["text"] == "city=Paris; population=2145906"

    def test_the_dataset_is_built_and_linked(self) -> None:
        outcome = _ingest("text/csv", CSV_BYTES)

        dataset = outcome.dataset
        assert dataset is not None
        assert dataset["dataset_id"].startswith("DATA_")
        assert dataset["source_id"] == SOURCE_ID
        assert dataset["row_count"] == 2
        assert dataset["dataset_schema"] == {"city": "string", "population": "string"}
        # §18.1 — the dataset points at the stored bytes, not at a temp copy.
        assert dataset["storage_ref"] == STORAGE_REF
        assert {unit["dataset_id"] for unit in outcome.units} == {dataset["dataset_id"]}

    def test_json_and_xml_records_are_read_too(self) -> None:
        json_outcome = _ingest("application/json", JSON_BYTES, file_name="cities.json")
        xml_outcome = _ingest("application/xml", XML_BYTES, file_name="cities.xml")

        assert len(json_outcome.units) == 2
        assert len(xml_outcome.units) == 2
        assert json_outcome.units[0]["location"]["kind"] == "row"

    def test_a_workbook_is_read_sheet_by_sheet(self) -> None:
        from openpyxl import Workbook

        buffer = io.BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["city", "population"])
        sheet.append(["Paris", 2145906])
        workbook.save(buffer)

        outcome = _ingest(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer.getvalue(),
            file_name="cities.xlsx",
        )

        assert len(outcome.units) == 1
        assert outcome.units[0]["content"]["values"] == {"city": "Paris", "population": 2145906}


class TestProseIngestion:
    """One unit per section, located by character offset."""

    def test_a_text_file_yields_one_unit_per_section(self) -> None:
        outcome = _ingest("text/plain", TEXT_BYTES, file_name="note.txt")

        assert [unit["content"]["text"] for unit in outcome.units] == [
            "Premier paragraphe.",
            "Second paragraphe.",
        ]
        assert [unit["location"]["section"] for unit in outcome.units] == [1, 2]
        assert outcome.units[1]["location"]["char_offset"] > 0
        assert all(unit["type"] == "document_fragment" for unit in outcome.units)

    def test_prose_units_carry_no_dataset(self) -> None:
        outcome = _ingest("text/plain", TEXT_BYTES, file_name="note.txt")

        assert outcome.dataset is None
        assert all(unit["dataset_id"] is None for unit in outcome.units)

    def test_an_empty_text_yields_no_unit_and_says_why(self) -> None:
        outcome = _ingest("text/plain", b"   \n\n  \n", file_name="vide.txt")

        assert outcome.units == []
        assert any("pas de texte lisible" in text for text in outcome.limitations)


class TestUnreadablePayloads:
    """§0.2/§37 — no unit is invented when the content cannot be read."""

    def test_a_corrupt_pdf_yields_no_unit_and_names_the_cause(self) -> None:
        outcome = _ingest("application/pdf", b"%PDF-1.7\ntronque", file_name="casse.pdf")

        assert outcome.units == []
        assert len(outcome.limitations) == 1
        assert "Aucune unité extraite" in outcome.limitations[0]

    def test_a_corrupt_json_yields_no_unit(self) -> None:
        outcome = _ingest("application/json", b"{ceci n est pas du json", file_name="x.json")

        assert outcome.units == []
        assert "Aucune unité extraite" in outcome.limitations[0]

    def test_an_empty_csv_yields_no_unit(self) -> None:
        outcome = _ingest("text/csv", b"city,population\n", file_name="vide.csv")

        assert outcome.units == []
        assert any("aucun enregistrement" in text for text in outcome.limitations)

    def test_an_unknown_type_is_refused_by_name(self) -> None:
        outcome = _ingest("image/png", b"\x89PNG\r\n\x1a\n", file_name="photo.png")

        assert outcome.units == []
        assert "image/png" in outcome.limitations[0]


class TestUnitContract:
    """Every produced unit satisfies §11, or it is not produced at all."""

    def test_units_are_validated_by_the_domain_entity(self) -> None:
        outcome = _ingest("text/csv", CSV_BYTES)

        for unit in outcome.units:
            assert unit["information_id"].startswith("INF_")
            assert unit["type"] in {"record", "document_fragment"}
            assert unit["data_stage"] == "raw"
            assert unit["provenance"]["method"] == "app.tools.files.read_csv"
            assert unit["provenance"]["extracted_from"] == STORAGE_REF
            assert unit["versions"] == [unit["information_id"]]
            # §15 — no confidence score is invented, and the nature is stated.
            assert unit["confidence"] == {"score": None, "not_a_probability": True}
            assert unit["language"] is None

    def test_the_ingestion_does_not_touch_the_bytes_it_reads(self) -> None:
        """The hash of the delivered document is the hash of what was stored."""
        digest = sha256_hex(CSV_BYTES)

        _ingest("text/csv", CSV_BYTES)

        assert sha256_hex(CSV_BYTES) == digest

    def test_an_empty_zip_workbook_is_not_a_dataset(self) -> None:
        """A ZIP that is not a workbook must not become a plausible dataset."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data/whatever.txt", "x")

        outcome = _ingest(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            buffer.getvalue(),
            file_name="faux.xlsx",
        )

        assert outcome.units == []
        assert "Aucune unité extraite" in outcome.limitations[0]
