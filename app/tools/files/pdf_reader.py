"""``read_pdf`` internal tool per §21.

``read_pdf(path)`` returns the §21 :class:`Document` envelope; the literal page
text is returned alongside it by :func:`read_pdf_text`. Tables are extracted
with ``pdfplumber`` (the §4.1 library already used by the PDF connector) and
returned as-is — no cell value is ever inferred from a neighbour (§1.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.document import Document
from app.tools.files.document_reader import build_document, extract_document_text

__all__ = ["read_pdf", "read_pdf_text", "read_pdf_tables"]


def read_pdf_text(path: str, *, source_id: str) -> tuple[Document, str]:
    """Return the PDF document envelope together with its literal text."""
    file_path = Path(path)
    if file_path.suffix.lower() != ".pdf":
        raise ValidationError(f"not a PDF file: {path}")
    return extract_document_text(path, source_id=source_id)


def read_pdf_tables(path: str) -> list[dict[str, Any]]:
    """Extract every detectable table from the PDF at *path*.

    Args:
        path: Path of the PDF file.

    Returns:
        One entry per table with its zero-based ``page`` (1-based page number),
        the ``table_index`` on that page, the ``rows`` as lists of cells and the
        ``column_count`` of the widest row.

    Raises:
        ValidationError: If the file is missing or is not a PDF.
        InfrastructureError: If ``pdfplumber`` is unavailable or the document
            cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"pdf file not found: {path}")
    if file_path.suffix.lower() != ".pdf":
        raise ValidationError(f"not a PDF file: {path}")

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - §4.1 pins pdfplumber
        raise InfrastructureError("pdfplumber is required to extract PDF tables") from exc

    tables: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table_index, table in enumerate(page.extract_tables() or []):
                    rows = [list(row) for row in table]
                    tables.append(
                        {
                            "page": page_number,
                            "table_index": table_index,
                            "rows": rows,
                            "row_count": len(rows),
                            "column_count": max((len(row) for row in rows), default=0),
                        }
                    )
    except Exception as exc:
        raise InfrastructureError(f"could not extract PDF tables: {exc}") from exc
    return tables


def read_pdf(path: str, *, source_id: str) -> Document:
    """Return the §21 ``Document`` envelope read from the PDF at *path*."""
    return build_document(path, source_id=source_id)
