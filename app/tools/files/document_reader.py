"""``extract_document`` internal tool per §21.

``extract_document(path)`` returns the §21 :class:`Document` envelope (identity,
MIME type, content hash, storage reference). The extracted text is returned
alongside it by :func:`extract_document_text`, so a caller never has to re-read
and re-decode the file to get at the content.

Text extraction uses the libraries mandated by §4.1 (``python-docx``, ``pypdf``)
and never summarises or rewrites the source: the returned string is the literal
document text, which is what makes it usable as evidence (§33.4).
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import InfrastructureError, ValidationError
from app.core.hashing import sha256_hex
from app.domain.entities.document import Document
from app.domain.value_objects.ulid import ULID

__all__ = ["extract_document", "extract_document_text", "build_document", "MIME_BY_SUFFIX"]

#: MIME types of the document formats INIS V1 ingests (§1.1).
MIME_BY_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".rst": "text/x-rst",
}

#: Suffixes whose text can be decoded directly from the file bytes.
_PLAIN_TEXT_SUFFIXES = frozenset({".txt", ".md", ".rst"})


def build_document(
    path: str,
    *,
    source_id: str,
    mime_type: str | None = None,
) -> Document:
    """Build the provenance-complete ``Document`` envelope of a local file.

    Args:
        path: Path of the file.
        source_id: Identifier of the owning source (§0.2).
        mime_type: Explicit MIME type; inferred from the suffix when omitted.

    Returns:
        The document entity carrying the SHA-256 of its exact bytes.

    Raises:
        ValidationError: If the file is missing or *source_id* is empty.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"document not found: {path}")
    if not source_id or not str(source_id).strip():
        raise ValidationError("source_id is required to build a provenance-complete Document")

    payload = file_path.read_bytes()
    return Document(
        document_id=ULID.new("DOC_"),
        source_id=source_id,
        mime_type=mime_type or MIME_BY_SUFFIX.get(file_path.suffix.lower(), "application/octet-stream"),
        content_hash=sha256_hex(payload),
        storage_ref=file_path.resolve().as_uri(),
    )


def _extract_pdf_text(path: Path) -> str:
    """Return the literal text of every PDF page, in page order."""
    import pypdf

    reader = pypdf.PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages)


def _extract_docx_text(path: Path) -> str:
    """Return the literal text of a ``.docx`` document, paragraph by paragraph."""
    import docx

    document = docx.Document(str(path))
    blocks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            blocks.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(blocks)


def extract_document_text(path: str, *, source_id: str) -> tuple[Document, str]:
    """Extract the literal text of *path* together with its document envelope.

    Args:
        path: Path of the document.
        source_id: Identifier of the owning source (§0.2).

    Returns:
        ``(document, text)``. Encrypted or unreadable documents raise instead of
        returning an empty string that would look like an empty document
        (§0.2, §25.1).

    Raises:
        ValidationError: If the file is missing.
        InfrastructureError: If the required §4.1 extraction library is absent
            or the document cannot be decoded.
    """
    file_path = Path(path)
    document = build_document(path, source_id=source_id)
    suffix = file_path.suffix.lower()

    if suffix in _PLAIN_TEXT_SUFFIXES:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return document, text

    if suffix == ".pdf":
        try:
            return document, _extract_pdf_text(file_path)
        except ImportError as exc:  # pragma: no cover - §4.1 pins pypdf
            raise InfrastructureError("pypdf is required to extract PDF text") from exc
        except Exception as exc:
            raise InfrastructureError(f"could not extract PDF text: {exc}") from exc

    if suffix == ".docx":
        try:
            return document, _extract_docx_text(file_path)
        except ImportError as exc:  # pragma: no cover - §4.1 pins python-docx
            raise InfrastructureError("python-docx is required to extract DOCX text") from exc
        except Exception as exc:
            raise InfrastructureError(f"could not extract DOCX text: {exc}") from exc

    if suffix in {".html", ".htm"}:
        return document, file_path.read_text(encoding="utf-8", errors="replace")

    raise InfrastructureError(f"unsupported document format: {suffix or path}")


def extract_document(path: str, *, source_id: str) -> Document:
    """Return the §21 ``Document`` envelope extracted from *path*."""
    document, _text = extract_document_text(path, source_id=source_id)
    return document
