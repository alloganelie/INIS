"""§11/§12.1 — turn an ingested document into traceable information units.

L2.1 stores what a client uploads; this module is what makes the stored bytes
*usable*. It reads them with the §21 readers and produces:

* one :class:`~app.domain.entities.information_unit.InformationUnit` **per
  record** for a tabular payload (CSV, JSON, XML, XLSX), **per page** for a PDF,
  **per paragraph** (then per table) for a DOCX, **per paragraph** for TXT/MD;
* one unit per literal text tag embedded in an image, plus one describing the
  image's own technical properties — **no OCR, no caption** (§9.2);
* the :class:`~app.domain.entities.dataset.Dataset` of a tabular payload, so the
  units can point at it (`DATA_`) and the export of L1 has something to describe;
* the limitations of what was *not* possible — never a unit invented to fill a
  gap (§24.3, §37).

Every unit is validated by the §11 entity before it leaves this module: a unit
without provenance, without a location, or with an unknown ``type`` is a bug
here, not a surprise in a delivery.

Four deliberate limits, stated rather than hidden:

* a payload the readers cannot parse (encrypted PDF, corrupt workbook) yields
  **no** unit and one explicit limitation;
* nothing is summarised: the sentences recorded inside a prose fragment are
  literal sentences of that fragment (``FactExtractor``, §21), and a fragment it
  cannot split keeps all its text in ``content["text"]`` — no sentence is ever
  paraphrased;
* a workbook with several sheets is read **one sheet at a time** — the sheet
  that was read is named in every row locator, and the sheets that were not read
  are named in ``limitations``: silently merging them would invent a dataset;
* beyond the ADR 007 threshold, extraction works **by chunks** (§41.6).
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import InisError
from app.core.time import utc_now
from app.domain.entities.dataset import Dataset
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID
from app.knowledge.extraction.fact_extractor import FactExtractor
from app.knowledge.normalization.chunked_dataset import DefaultChunkedDatasetProcessor
from app.knowledge.normalization.limits import chunked_processing_config
from app.tools.files.csv_reader import load_csv
from app.tools.files.dataset_builder import build_dataset
from app.tools.files.document_reader import extract_document_blocks
from app.tools.files.excel_reader import list_sheets, load_excel
from app.tools.files.json_reader import load_json
from app.tools.files.xml_reader import load_xml
from app.tools.images.image_analyzer import extract_image_content

__all__ = [
    "IMAGE_SUFFIXES",
    "TABULAR_MIME_TYPES",
    "TEXT_MIME_TYPES",
    "IngestionOutcome",
    "block_sentences",
    "fragment_unit",
    "ingest_document",
    "reader_for",
    "record_units",
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

#: Types read as prose: one unit per page (PDF), paragraph (DOCX/TXT/MD) or table.
TEXT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

#: §9.1 — images the Pillow connector reads (optional dependency, decision D6),
#: with the suffix given to the temporary copy. The list is deliberately explicit
#: and drift-locked by ``tests/unit/knowledge/test_document_ingestor.py`` against
#: ``app.connectors.images.image_connector.MIME_TYPES``: an image type this module
#: claims to ingest but the connector cannot decode would be an empty promise.
IMAGE_SUFFIXES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}

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
    **IMAGE_SUFFIXES,
}

#: Types whose records live in a *sheet*: the locator has to name it (§11).
_SPREADSHEET_MIME_TYPES: frozenset[str] = frozenset(
    {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
)

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
    **{
        mime_type: "app.tools.images.extract_image_content"
        for mime_type in IMAGE_SUFFIXES
    },
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
    return utc_now().isoformat()


def _row_text(row: dict) -> str:
    """Render one record as ``key=value`` pairs, in a stable order."""
    return "; ".join(f"{key}={row[key]}" for key in sorted(row))


def _read_tabular(
    mime_type: str, path: str, source_id: str
) -> tuple[Dataset, list[dict], list[str]]:
    """Read a tabular payload with the matching §21 reader.

    Returns:
        ``(dataset, rows, notes)``. The notes are the limits of the read itself:
        a workbook holding several sheets is read one sheet at a time, so the
        names of the sheets that were **not** read are returned here — the caller
        turns them into a limitation instead of presenting one sheet as the whole
        workbook (§0.2).
    """
    if mime_type == "text/csv":
        dataset, rows = load_csv(path, source_id=source_id)
        return dataset, rows, []
    if mime_type == "application/json":
        dataset, rows = load_json(path, source_id=source_id)
        return dataset, rows, []
    if mime_type == "application/xml":
        dataset, rows = load_xml(path, source_id=source_id)
        return dataset, rows, []

    sheets = list_sheets(path)
    dataset, rows = load_excel(path, source_id=source_id)
    if len(sheets) <= 1:
        return dataset, rows, []
    return dataset, rows, [
        (
            "Seule la première feuille du classeur a été lue : les autres feuilles "
            f"({', '.join(sheets[1:])}) ne sont pas ingérées (aucune feuille n'est "
            "fusionnée implicitement, §0.2)."
        )
    ]


def _read_blocks(mime_type: str, path: str, source_id: str) -> list[dict]:
    """Read a prose payload as locatable blocks with the matching §21 reader.

    Returns:
        One block per page (PDF), paragraph and table (DOCX) or blank-line
        separated paragraph (TXT/MD). The blocks keep the empty pages of a PDF:
        the caller decides what an empty page means, this module never renumbers
        a document.
    """
    _document, blocks = extract_document_blocks(path, source_id=source_id)
    return blocks


async def _chunked_units(
    items: list[Any],
    *,
    build_one: Any,
    dataset_id: str,
    threshold: int | None = None,
) -> tuple[list[dict], list[str]]:
    """Return one §11 unit per item, chunked beyond the ADR 007 threshold (§41.6).

    Args:
        items: The rows of a tabular payload, or the blocks of a prose one.
        build_one: ``item -> unit dict``; the only step that scales with the
            number of items, which is what chunking bounds.
        dataset_id: Identifier stamped on the §41.6 chunks (the dataset for a
            tabular payload, the document for a prose one).
        threshold: Explicit ADR 007 ceiling; resolved from the environment and
            the ADR default when omitted.

    Returns:
        ``(units, errors)``. Beyond the threshold, ``DefaultChunkedDatasetProcessor``
        streams the items in chunks of at most ``chunk_size_rows`` and merges the
        results **in order**, so the output is identical to the direct path; an
        item that cannot become a unit is dropped *and named* rather than
        silently lost.

    The dataset itself is not rebuilt here: §41.6 provides no incremental schema
    merge, so the schema of a tabular payload is still inferred from the rows the
    reader returned (see :func:`ingest_document`, which states this bound).
    """
    config = chunked_processing_config(threshold)
    if not config.should_stream(len(items)):
        units: list[dict] = []
        errors: list[str] = []
        for index, item in enumerate(items, start=1):
            try:
                units.append(build_one(item))
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed
                errors.append(f"item {index}: {exc}")
        return units, errors

    processor = DefaultChunkedDatasetProcessor(
        items, dataset_id=dataset_id, config=config, transform=build_one
    )
    merged = await processor.run()
    return list(merged["rows"]), list(merged["errors"])


def _unit_errors(errors: list[str], total: int) -> list[str]:
    """Return the §25.2 limitation naming the units that could not be produced."""
    if not errors:
        return []
    return [
        f"{len(errors)} unité(s) §11 non produite(s) sur {total} : {errors[0]}"
        + (f" (et {len(errors) - 1} autre(s))" if len(errors) > 1 else "")
    ]


def _base_unit(
    *,
    unit_type: str,
    content: dict,
    location: dict,
    document_id: str | None,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
    dataset_id: str | None,
    method: str,
    origin: str = "uploaded_document",
    raw_reference: Mapping[str, Any] | None = None,
) -> InformationUnit:
    """Build one §11 unit, validated by the domain entity.

    ``raw_reference`` and ``origin`` are overridable because a second producer
    exists since L2.5: a PostgreSQL table read by ``postgres_query`` (§36.7)
    produces record units located in a *table*, not in an uploaded document, and
    its lineage must not claim an origin it does not have.

    Raises:
        ValidationError: When the unit would violate §11 (no provenance, an
            unknown type), which is a bug here rather than a bad input.
    """
    information_id = ULID.new("INF_")
    now = _now()
    raw = dict(raw_reference) if raw_reference is not None else {
        "document_id": document_id,
        "file_name": file_name,
        "storage_ref": storage_ref,
        "mime_type": mime_type,
    }
    raw["location"] = location
    unit = InformationUnit(
        information_id=information_id,
        type=unit_type,
        content=content,
        raw_reference=raw,
        source_id=source_id,
        document_id=document_id,
        dataset_id=dataset_id,
        location=location,
        context={"request_id": request_id, "origin": origin},
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
        # §12 — the reader that produced this unit *is* the normalisation step:
        # it turned a page, a paragraph or a row into a located §11 unit, so the
        # unit is born « normalized » and never claims to be the untouched
        # material (the stored bytes are the `raw` stage of §9.1).
        data_stage="normalized",
        created_at=now,
        updated_at=now,
    )
    unit.validate()
    return unit


def _record_unit(
    row: Mapping[str, Any],
    *,
    index: int,
    dataset: Dataset,
    source_id: str,
    request_id: str,
    document_id: str | None,
    file_name: str,
    storage_ref: str,
    mime_type: str,
    method: str,
    origin: str,
    raw_reference: Mapping[str, Any] | None,
    sheet: str | None,
) -> dict:
    """Build the §11 ``record`` unit of one row of *dataset*.

    The locator names the row **and**, when the payload is a workbook, the sheet
    that row lives in: "row 2" of a multi-sheet workbook is not a position until
    the sheet is named (§11).
    """
    location: dict[str, Any] = {
        "kind": "row",
        "row": index,
        "dataset_id": dataset.dataset_id,
        "columns": sorted(row),
    }
    if sheet:
        location["sheet"] = sheet
    return _base_unit(
        unit_type="record",
        content={"values": dict(row), "text": _row_text(dict(row))},
        location=location,
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name=file_name,
        storage_ref=storage_ref,
        mime_type=mime_type,
        dataset_id=dataset.dataset_id,
        method=method,
        origin=origin,
        raw_reference=raw_reference,
    ).model_dump(mode="json")


def record_units(
    *,
    rows: list[dict],
    dataset: Dataset,
    source_id: str,
    request_id: str,
    document_id: str | None = None,
    file_name: str = "",
    storage_ref: str = "",
    mime_type: str = "",
    method: str | None = None,
    origin: str = "uploaded_document",
    raw_reference: Mapping[str, Any] | None = None,
    sheet: str | None = None,
) -> list[dict]:
    """Return one §11 ``record`` unit per row, each with its row locator.

    Public since L2.5 because two producers build record units: the ingestion of
    an uploaded document (§9.1) and the read of a PostgreSQL table (§36.7). Both
    need the same localisation and the same §11 validation, and each keeps its own
    ``method``/``origin`` so the §12.1 lineage can tell which one ran — an
    aggregate unit attributed to the wrong producer is a fabrication (§0.2).

    The ingestion of an **uploaded** payload goes through :func:`_chunked_units`
    instead, so a file beyond the ADR 007 threshold is turned into units chunk by
    chunk; this function keeps the direct, row by row behaviour that the database
    read (already a bounded page of rows) relies on.
    """
    method = method or _READERS.get(mime_type, "app.tools.files.read_csv")
    return [
        _record_unit(
            row,
            index=index,
            dataset=dataset,
            source_id=source_id,
            request_id=request_id,
            document_id=document_id,
            file_name=file_name,
            storage_ref=storage_ref,
            mime_type=mime_type,
            method=method,
            origin=origin,
            raw_reference=raw_reference,
            sheet=sheet,
        )
        for index, row in enumerate(rows, start=1)
    ]


def fragment_unit(
    block: Mapping[str, Any],
    *,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
    sentences: Sequence[str] = (),
) -> dict:
    """Return the §11 ``document_fragment`` unit of one locatable block.

    The block comes from
    :func:`app.tools.files.document_reader.extract_document_blocks`, so its
    position is provable: ``kind`` (``page``, ``paragraph``, ``table``,
    ``section``), the ``index`` of that piece in its own document, and the
    ``char_offset``/``characters`` of the text inside the extracted document.

    ``sentences`` are the literal sentences of the block, as read by
    ``FactExtractor`` (§21). They are recorded *inside* the fragment — next to
    the full text, never instead of it: a block the splitter cannot cut (a
    paragraph shorter than its floor) keeps all of its text and simply carries no
    sentence, which is why an empty list here loses nothing (§11.1).
    """
    text = str(block.get("text") or "")
    kind = str(block.get("kind") or "section")
    index = int(block.get("index") or 0)
    location: dict[str, Any] = {
        "kind": kind,
        kind: index,
        "char_offset": int(block.get("char_offset") or 0),
        "characters": int(block.get("characters") or len(text)),
    }
    content: dict[str, Any] = {"text": text}
    if sentences:
        content["sentences"] = list(sentences)
    return _base_unit(
        unit_type="document_fragment",
        content=content,
        location=location,
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name=file_name,
        storage_ref=storage_ref,
        mime_type=mime_type,
        dataset_id=None,
        method=_READERS.get(mime_type, "app.tools.files.extract_document"),
    ).model_dump(mode="json")


async def block_sentences(
    block: Mapping[str, Any],
    *,
    source_id: str,
    document_id: str,
    extracted_from: str,
) -> list[str]:
    """Return the literal sentences ``FactExtractor`` reads inside *block*.

    Args:
        block: One block of :func:`extract_document_blocks`.
        source_id: Identifier of the owning source (§0.2).
        document_id: Identifier of the document the block belongs to.
        extracted_from: Where the bytes live — the object reference, never the
            temporary ``file://`` path the reader worked on (§18.1).

    Returns:
        The sentences, verbatim and in reading order, or an empty list for a
        block the splitter considers too short to be a fact. Nothing is
        paraphrased and nothing is invented: every sentence is a substring of the
        block text (§1.2).
    """
    facts = await FactExtractor().extract(
        text=str(block.get("text") or ""),
        source_id=source_id,
        document_id=document_id,
        url=extracted_from,
    )
    return [str(fact["content"]["text"]) for fact in facts]


async def _image_units(
    *,
    path: str,
    document_id: str,
    source_id: str,
    request_id: str,
    file_name: str,
    storage_ref: str,
    mime_type: str,
) -> tuple[list[dict], list[str]]:
    """Return the §11 units of an image, plus the limits of what it supports (§9.1).

    The units come from ``extract_image_content`` (§21): one per literal text tag
    embedded in the file, then one describing the image's technical properties.
    Two things are rewritten on the way out, because the tool cannot know them:

    * ``raw_reference`` and ``provenance.extracted_from`` point at the **stored
      object**, never at the temporary copy the tool read (a ``file://`` path
      that dies with this function, §18.1);
    * ``context`` names the request and the origin, like every other ingested
      unit.

    No OCR, no caption: an image carrying no text therefore yields its properties
    unit only, and an unavailable Pillow yields **no** unit at all — the
    degradation is reported as an explicit limitation instead of a description of
    the picture (§9.2, §0.2).
    """
    try:
        extracted = await extract_image_content(
            path, source_id=source_id, document_id=document_id
        )
    except InisError as exc:
        return [], [
            (
                f"Aucune unité extraite : {type(exc).__name__} — {exc}. Pillow est une "
                "dépendance optionnelle (pillow_available=False, décision D6) et INIS "
                "V1 n'a aucun OCR (§9.2) : rien n'est décrit à la place de l'image."
            )
        ]

    units: list[dict] = []
    for unit in extracted:
        item = unit.model_dump(mode="json")
        location = dict(item.get("location") or {})
        item["raw_reference"] = {
            "document_id": document_id,
            "file_name": file_name,
            "storage_ref": storage_ref,
            "mime_type": mime_type,
            "location": location,
        }
        provenance = dict(item.get("provenance") or {})
        provenance.pop("storage_ref", None)
        provenance["extracted_from"] = storage_ref
        provenance["document_id"] = document_id
        provenance["request_id"] = request_id
        provenance["method"] = _READERS[mime_type]
        item["provenance"] = provenance
        item["context"] = {"request_id": request_id, "origin": "uploaded_image"}
        # §18.1 — a stored unit is its own first version (the tool mints the id).
        item["versions"] = [item["information_id"]]
        units.append(item)

    return units, [
        (
            "Unités « image_region » issues des textes réellement embarqués dans le "
            "fichier et de ses propriétés techniques : INIS V1 n'a ni OCR ni légende "
            "(§9.2), aucune description de l'image n'est inventée."
        )
    ]


async def ingest_document(
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

    Beyond the ADR 007 threshold, the units are built **chunk by chunk**
    (:func:`_chunked_units`, §41.6). What that bounds is the unit construction —
    one ULID and one §11 validation per row/page — not the dataset schema, which
    is still inferred from the rows the reader returned.
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

        if mime_type in IMAGE_SUFFIXES:
            units, limits = await _image_units(
                path=path,
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name=file_name,
                storage_ref=storage_ref,
                mime_type=mime_type,
            )
            outcome.units = units
            outcome.limitations.extend(limits)
            return outcome

        if mime_type in TABULAR_MIME_TYPES:
            try:
                dataset, rows, notes = _read_tabular(mime_type, path, source_id)
            except InisError as exc:
                outcome.limitations.append(
                    f"Aucune unité extraite : {type(exc).__name__} — {exc}"
                )
                return outcome
            outcome.limitations.extend(notes)
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
            sheet = (
                list_sheets(path)[0] if mime_type in _SPREADSHEET_MIME_TYPES else None
            )
            indexed: list[tuple[int, dict]] = list(enumerate(rows, start=1))
            units, errors = await _chunked_units(
                indexed,
                build_one=lambda pair: _record_unit(
                    pair[1],
                    index=pair[0],
                    dataset=dataset,
                    source_id=source_id,
                    request_id=request_id,
                    document_id=document_id,
                    file_name=file_name,
                    storage_ref=storage_ref,
                    mime_type=mime_type,
                    method=_READERS.get(mime_type, "app.tools.files.read_csv"),
                    origin="uploaded_document",
                    raw_reference=None,
                    sheet=sheet,
                ),
                dataset_id=dataset.dataset_id,
            )
            outcome.units = units
            outcome.limitations.extend(_unit_errors(errors, len(rows)))
            return outcome

        try:
            blocks = _read_blocks(mime_type, path, source_id)
        except InisError as exc:
            outcome.limitations.append(
                f"Aucune unité extraite : {type(exc).__name__} — {exc}"
            )
            return outcome

        readable = [
            block for block in blocks if str(block.get("text") or "").strip()
        ]
        if not readable:
            outcome.limitations.append(
                "Aucune unité extraite : le document ne contient pas de texte lisible "
                "(document scanné ou protégé ?)."
            )
            return outcome

        annotated: list[tuple[dict, list[str]]] = []
        for block in readable:
            annotated.append(
                (
                    block,
                    await block_sentences(
                        block,
                        source_id=source_id,
                        document_id=document_id,
                        extracted_from=storage_ref,
                    ),
                )
            )

        units, errors = await _chunked_units(
            annotated,
            build_one=lambda pair: fragment_unit(
                pair[0],
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name=file_name,
                storage_ref=storage_ref,
                mime_type=mime_type,
                sentences=pair[1],
            ),
            dataset_id=document_id,
        )
        outcome.units = units
        outcome.limitations.extend(_unit_errors(errors, len(readable)))
        outcome.limitations.extend(_prose_limits(mime_type, blocks, readable))
        return outcome


def _prose_limits(
    mime_type: str, blocks: list[dict], readable: list[dict]
) -> list[str]:
    """Return what the prose extraction of *mime_type* could not cover.

    Only what is true is listed: the empty pages of a PDF (no OCR, §9.2) and the
    granularity that *was* used, so a reader never has to guess where a fragment
    sits in the document.
    """
    limits: list[str] = []
    if mime_type == "application/pdf":
        empty_pages = len(blocks) - len(readable)
        if empty_pages:
            limits.append(
                f"{empty_pages} page(s) du PDF sans texte extractible (couche texte "
                "absente) : aucun OCR n'est disponible en V1 (§9.2), aucune unité "
                "n'est inventée pour une page illisible."
            )
        limits.append(
            "Unités « document_fragment » localisées par page (le numéro de page est "
            "l'ordre du document) et décalage de caractères dans le texte extrait."
        )
    if mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        paragraphs = sum(1 for block in blocks if block.get("kind") == "paragraph")
        tables = sum(1 for block in blocks if block.get("kind") == "table")
        limits.append(
            "Unités « document_fragment » localisées par paragraphe "
            f"({len(readable)} bloc(s) : {paragraphs} paragraphe(s), {tables} "
            "tableau(x)) et décalage de caractères dans le texte extrait."
        )
    return limits
