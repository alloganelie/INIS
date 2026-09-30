"""File generators for the §24.2 delivery artifacts (CSV, JSON, XML, XLSX).

One entry point — :func:`generate_artifact` — so the packager never has to know
which module handles which format, and so every unsupported request fails at the
same place with the same, explicit ``ValidationError`` (§25.2, §37).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.artifacts.generators.csv_generator import generate_csv
from app.artifacts.generators.json_generator import generate_json
from app.artifacts.generators.pdf_generator import (
    PDF_AVAILABLE,
    PDF_UNAVAILABLE_REASON,
    generate_pdf,
    pdf_supported,
)
from app.artifacts.generators.tabular import cell_text, default_columns
from app.artifacts.generators.xlsx_generator import generate_xlsx
from app.artifacts.generators.xml_generator import generate_xml
from app.core.errors import ValidationError

__all__ = [
    "AVAILABLE_FORMATS",
    "EXTENSIONS",
    "FILE_FORMATS",
    "MIME_TYPES",
    "PDF_AVAILABLE",
    "PDF_UNAVAILABLE_REASON",
    "GeneratedFile",
    "cell_text",
    "default_columns",
    "file_formats_message",
    "generate_artifact",
    "generate_csv",
    "generate_json",
    "generate_pdf",
    "generate_xlsx",
    "generate_xml",
    "pdf_supported",
]

#: MIME type of each deliverable format (§24.2 ``mime_type``).
MIME_TYPES: dict[str, str] = {
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

#: File extension of each deliverable format.
EXTENSIONS: dict[str, str] = {
    "csv": "csv",
    "json": "json",
    "xml": "xml",
    "xlsx": "xlsx",
    "pdf": "pdf",
}

#: Format names the §24 delivery contract knows about.
FILE_FORMATS: tuple[str, ...] = ("csv", "json", "xml", "xlsx", "pdf")

#: Formats this stack can actually produce (``pdf`` is refused, §4.1).
AVAILABLE_FORMATS: tuple[str, ...] = tuple(
    fmt for fmt in FILE_FORMATS if fmt != "pdf" or pdf_supported()
)

#: Characters a generated file name may contain.
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]")


def file_formats_message() -> str:
    """Return the sentence listing the formats a delivery can actually produce."""
    return f"Formats de livraison disponibles : {', '.join(AVAILABLE_FORMATS)}."


@dataclass(frozen=True)
class GeneratedFile:
    """One generated file: its bytes, its name and its MIME type (§24.2)."""

    content: bytes
    file_name: str
    mime_type: str


def _file_stem(stem: str) -> str:
    """Return *stem* as a safe base name (no separator, no traversal)."""
    cleaned = _SAFE_STEM.sub("_", str(stem or "delivery"))
    return cleaned.strip("._") or "delivery"


def generate_artifact(
    output_format: str,
    *,
    file_stem: str,
    payload: Mapping[str, Any] | None = None,
    rows: Sequence[Mapping[str, Any]] | None = None,
    columns: Sequence[str] | None = None,
    sheets: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> GeneratedFile:
    """Return the file for *output_format* (§24.2/§24.3).

    Args:
        output_format: One of :data:`FILE_FORMATS`. ``evidence_package`` is *not*
            a file format: it is the §24.1 JSON response itself and is refused
            here rather than turned into a fake document.
        file_stem: Base name of the file, without extension.
        payload: The §24.1 delivery payload (used by JSON and XML).
        rows: Tabular projection of the requested dataset (CSV and XLSX).
        columns: Column order of the tabular export; sorted union of the row
            keys when omitted.
        sheets: Full §24.3 workbook description (XLSX); when omitted the
            ``data`` sheet is built from *rows*.

    Returns:
        The :class:`GeneratedFile` to store.

    Raises:
        ValidationError: When the format is unknown, is not a file format, or is
            a known format this stack cannot produce (``pdf``, §4.1).
    """
    fmt = str(output_format or "").lower()
    if fmt == "evidence_package":
        raise ValidationError(
            "evidence_package is not a file format: it is delivered as the §24.1 "
            "JSON response, and no artifact file is attached to it."
        )
    if fmt not in FILE_FORMATS:
        raise ValidationError(
            f"Unknown output format '{output_format}': §24 knows "
            f"{', '.join(FILE_FORMATS)} (and evidence_package)."
        )

    file_name = f"{_file_stem(file_stem)}.{EXTENSIONS[fmt]}"
    if fmt == "csv":
        content = generate_csv(rows or [], columns=columns)
    elif fmt == "xlsx":
        content = generate_xlsx(
            sheets if sheets is not None else {"data": list(rows or [])},
            columns=columns,
        )
    elif fmt == "json":
        content = generate_json(dict(payload or {}))
    elif fmt == "xml":
        content = generate_xml(dict(payload or {}))
    else:  # pragma: no cover - only 'pdf' can reach this branch today
        content = generate_pdf(dict(payload or {}))

    return GeneratedFile(content=content, file_name=file_name, mime_type=MIME_TYPES[fmt])
