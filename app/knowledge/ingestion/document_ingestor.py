"""§11/§12.1 — turn an ingested document into traceable information units.

L2.1 stores what a client uploads; this module is what makes the stored bytes
*usable*. It reads them with the §21 readers and produces:

* one :class:`~app.domain.entities.artifact`-style §11 unit **per record** for a
  tabular payload (CSV, JSON, XML, XLSX) or **per section** for a text payload
  (TXT, Markdown, PDF, DOCX);
* the :class:`~app.domain.entities.dataset.Dataset` of a tabular payload, so the
  units can point at it (`DATA_`) and the export of L1 has something to describe;
* the limitations of what was *not* possible — never a unit invented to fill a
  gap (§24.3, §37).

Every unit is validated by the §11 entity before it leaves this module: a unit
without provenance, without a location, or with an unknown ``type`` is a bug
here, not a surprise in a delivery.

Two deliberate limits, stated rather than hidden:

* the PDF path uses the whole extracted text: the page number is unknown, so the
  locator says ``kind="section"`` with the character offset and the extraction
  method, instead of claiming a page it cannot prove;
* a payload the readers cannot parse (encrypted PDF, corrupt workbook) yields
  **no** unit and one explicit limitation.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.core.errors import InisError
from app.domain.entities.dataset import Dataset
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID
from app.tools.files.csv_reader import load_csv
from app.tools.files.dataset_builder import build_dataset
from app.tools.files.document_reader import extract_document_text
from app.tools.files.excel_reader import load_excel
from app.tools.files.json_reader import load_json
from app.tools.files.pdf_reader import read_pdf_text
from app.tools.files.xml_reader import load_xml

__all__ = [
    "TABULAR_MIME_TYPES",
    "TEXT_MIME_TYPES",
    "IngestionOutcome",
    "ingest_document",
    "reader_for",
]

#: Types read as a table: one unit per record.
TABULAR_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/csv",
        "application/json",
        "application/xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)

#: Types read as prose: one unit per section.
TEXT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

#: MIME type → file suffix used for the temporary copy the readers require.
_SUFFIXES: dict[str, str] = {
    "text/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

#: §21 reader that produced a unit, per MIME type (the provenance `method`).
_READERS: dict[str, str] = {
    "text/csv": "app.tools.files.read_csv",
    "application/json": "app.tools.files.read_json",
    "application/xml": "app.tools.files.read_xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "app.tools.files.read_excel",
    "text/plain": "app.tools.files.extract_document",
    "text/markdown": "app.tools.files.extract_document",
    "application/pdf": "app.tools.files.read_pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "app.tools.files.extract_document",
}


def reader_for(mime_type: str | None) -> str:
    """Return the §21 reader name that reads *mime_type* (``read_csv``, …).

    Public because the pipeline has to name the tool a ``file_ingest`` step used
    in the §12.1 lineage: the reader that ran is the tool of the ``raw`` stage,
    never a generic ``DocumentIngestor`` when a specific one is known.
    """
    qualified = _READERS.get(str(mime_type or ""), "app.tools.files.extract_document")
    return qualified.rsplit(".", 1)[-1]


@dataclass
class IngestionOutcome:
    """What the ingestion of one document produced (a mutable accumulator)."""

    units: list[dict] = field(default_factory=list)
    dataset: dict | None = None
    limitations: list[str] = field(default_factory=list)


def _now() -> str:
    """Return the current UTC instant as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _row_text(row: dict) -> str:
    """Render one record as ``key=value`` pairs, in a stable order."""
    return "; ".join(f"{key}={row[key]}" for key in sorted(row))


def _sections(text: str) -> list[tuple[int, str]]:
    """Return ``(char_offset, text)`` for every non-empty paragraph.

    A paragraph is the smallest locatable piece of prose this module can claim:
    the offset lets a reader find it again in the original document (§11).
    """
    sections: list[tuple[int, str]] = []
    offset = 0
    for block in text.split("\n\n"):
        stripped = block.strip()
        if stripped:
            sections.append((offset, stripped))
        offset += len(block) + 2
    return sections


def _read_tabular(mime_type: str, path: str, source_id: str) -> tuple[Dataset, list[dict]]:
    """Read a tabular payload with the matching §21 reader."""
    if mime_type == "text/csv":
        return load_csv(path, source_id=source_id)
    if mime_type == "application/json":
        return load_json(path, source_id=source_id)
    if mime_type == "application/xml":
        return load_xml(path, source_id=source_id)
    return load_excel(path, source_id=source_id)


def _read_text(mime_type: str, path: str, source_id: str) -> str:
    """Read a prose payload with the matching §21 reader."""
    if mime_type == "application/pdf":
        return read_pdf_text(path, source_id=source_id)[1]
    if mime_type == "text/plain" or mime_type == "text/markdown":
        return read_text_file(path)
    return extract_document_text(path, source_id=source_id)[1]


def read_text_file(path: str) -> str:
    """Return the UTF-8 text of *path* (helper kept explicit for the reader dispatch)."""
    return Path(path).read_text(encoding="utf-8-sig")


def _base_unit(
    *,
    unit_type: str,
    content: dict,
    location: dict,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
    dataset_id: str | None,
    method: str,
) -> InformationUnit:
    """Build one §11 unit, validated by the domain entity.

    Raises:
        ValidationError: When the unit would violate §11 (no provenance, an
            unknown type), which is a bug here rather than a bad input.
    """
    information_id = ULID.new("INF_")
    now = _now()
    unit = InformationUnit(
        information_id=information_id,
        type=unit_type,
        content=content,
        raw_reference={
            "document_id": document_id,
            "file_name": file_name,
            "storage_ref": storage_ref,
            "mime_type": mime_type,
            "location": location,
        },
        source_id=source_id,
        document_id=document_id,
        dataset_id=dataset_id,
        location=location,
        context={"request_id": request_id, "origin": "uploaded_document"},
        language=None,
        unit=None,
        time={},
        classification={},
        quality={},
        confidence={"score": None, "not_a_probability": True},
        provenance={
            "extracted_from": storage_ref,
            "document_id": document_id,
            "method": method,
            "request_id": request_id,
        },
        versions=[information_id],
        data_stage="raw",
        created_at=now,
        updated_at=now,
    )
    unit.validate()
    return unit


def _record_units(
    *,
    rows: list[dict],
    dataset: Dataset,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
) -> list[dict]:
    """Return one §11 ``record`` unit per row, each with its row locator."""
    method = _READERS.get(mime_type, "app.tools.files.read_csv")
    units: list[dict] = []
    for index, row in enumerate(rows, start=1):
        location = {
            "kind": "row",
            "row": index,
            "dataset_id": dataset.dataset_id,
            "columns": sorted(row),
        }
        units.append(
            _base_unit(
                unit_type="record",
                content={"values": dict(row), "text": _row_text(row)},
                location=location,
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name=file_name,
                storage_ref=storage_ref,
                mime_type=mime_type,
                dataset_id=dataset.dataset_id,
                method=method,
            ).model_dump(mode="json")
        )
    return units


def _section_units(
    *,
    text: str,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
) -> list[dict]:
    """Return one §11 ``document_fragment`` unit per non-empty section."""
    method = _READERS.get(mime_type, "app.tools.files.extract_document")
    units: list[dict] = []
    for index, (offset, section) in enumerate(_sections(text), start=1):
        location = {
            "kind": "section",
            "section": index,
            "char_offset": offset,
            "characters": len(section),
        }
        units.append(
            _base_unit(
                unit_type="document_fragment",
                content={"text": section},
                location=location,
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name=file_name,
                storage_ref=storage_ref,
                mime_type=mime_type,
                dataset_id=None,
                method=method,
            ).model_dump(mode="json")
        )
    return units


def ingest_document(
    *,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    mime_type: str,
    data: bytes,
    storage_ref: str,
) -> IngestionOutcome:
    """Extract the §11 units (and the dataset) of one stored document.

    Args:
        document_id: ``DOC_`` identifier of the stored document (§9.1).
        source_id: ``SRC_`` identifier of the source it was uploaded for (§9).
        request_id: The request the document belongs to.
        file_name: Stored file name, used in the unit's ``raw_reference``.
        mime_type: The type *proved by the bytes* (§9.1).
        data: The document bytes, as stored in object storage.
        storage_ref: Where those bytes live (§18.1).

    Returns:
        The units, the dataset (tabular payloads only), and the limitations of
        what could not be done. An unreadable payload yields **no** unit and one
        explicit limitation: inventing one would put untraceable content in a
        delivery (§0.2).

    The bytes are copied to a temporary directory because the §21 readers take a
    path; the copy is deleted before returning, so nothing leaks to disk.
    """
    outcome = IngestionOutcome()
    if mime_type not in _SUFFIXES:
        outcome.limitations.append(
            f"Aucune unité extraite : le type {mime_type} n'a pas de lecteur §21 "
            "(voir la liste blanche de l'ingestion, §9.1)."
        )
        return outcome

    with tempfile.TemporaryDirectory(prefix="inis-ingest-") as workdir:
        path = str(Path(workdir) / f"document{_SUFFIXES[mime_type]}")
        Path(path).write_bytes(data)

        if mime_type in TABULAR_MIME_TYPES:
            try:
                dataset, rows = _read_tabular(mime_type, path, source_id)
            except InisError as exc:
                outcome.limitations.append(
                    f"Aucune unité extraite : {type(exc).__name__} — {exc}"
                )
                return outcome
            if not rows:
                outcome.limitations.append(
                    "Aucune unité extraite : le document est lisible mais ne contient "
                    "aucun enregistrement (§24.3 : aucune valeur inventée)."
                )
                return outcome
            # The dataset is rebuilt with the *object storage* reference: the
            # readers report a `file://` path, which dies with the temporary copy.
            dataset = build_dataset(
                rows,
                source_id=source_id,
                storage_ref=storage_ref,
                dataset_id=dataset.dataset_id,
            )
            outcome.dataset = dataset.model_dump(mode="json")
            outcome.units = _record_units(
                rows=rows,
                dataset=dataset,
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name=file_name,
                storage_ref=storage_ref,
                mime_type=mime_type,
            )
            return outcome

        try:
            text = _read_text(mime_type, path, source_id)
        except InisError as exc:
            outcome.limitations.append(
                f"Aucune unité extraite : {type(exc).__name__} — {exc}"
            )
            return outcome

        if not text.strip():
            outcome.limitations.append(
                "Aucune unité extraite : le document ne contient pas de texte lisible "
                "(document scanné ou protégé ?)."
            )
            return outcome

        outcome.units = _section_units(
            text=text,
            document_id=document_id,
            source_id=source_id,
            request_id=request_id,
            file_name=file_name,
            storage_ref=storage_ref,
            mime_type=mime_type,
        )
        if mime_type in (
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            outcome.limitations.append(
                "Unités « document_fragment » localisées par section et décalage de "
                "caractères : la granularité page/feuille de ce format n'est pas encore "
                "extraite (aucun numéro de page n'est inventé)."
            )
        return outcome
