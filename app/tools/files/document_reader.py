"""``extract_document`` internal tool per §21.

``extract_document(path)`` returns the §21 :class:`Document` envelope (identity,
MIME type, content hash, storage reference). The extracted text is returned
alongside it by :func:`extract_document_text`, and **located** by
:func:`extract_document_blocks`, so a caller never has to re-read and re-decode
the file to get at the content — nor to guess where in the document a piece of
it sits.

Text extraction uses the libraries mandated by §4.1 (``python-docx``, ``pypdf``)
and never summarises or rewrites the source: the returned string is the literal
document text, which is what makes it usable as evidence (§33.4).

Granularity is *declared*, never guessed. A ``.pdf`` is read page by page
(``pypdf``), a ``.docx`` paragraph by paragraph plus its tables, and a plain
text payload paragraph by paragraph. Every block carries its ``char_offset`` in
the extracted text, so the position it claims is verifiable:
``text[char_offset:char_offset + characters] == block["text"]``. An offset no
one can check would be a fabricated position (§0.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.errors import InfrastructureError, ValidationError
from app.core.hashing import sha256_hex
from app.domain.entities.document import Document
from app.domain.value_objects.ulid import ULID

__all__ = [
    "BLOCK_KINDS",
    "MIME_BY_SUFFIX",
    "build_document",
    "extract_document",
    "extract_document_blocks",
    "extract_document_text",
]

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

#: Suffixes read as an HTML document (decoded, never parsed into a DOM here).
_HTML_SUFFIXES = frozenset({".html", ".htm"})

#: Kinds a locatable block can claim (``location["kind"]`` upstream, §11).
BLOCK_KINDS: tuple[str, ...] = ("page", "paragraph", "table", "section")

#: What separates two extracted blocks. The offsets below are measured on the
#: text this separator produces, so the block position stays verifiable.
_BLOCK_SEPARATOR = "\n"


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


def _blocks(entries: list[tuple[str, int, str]], *, raw_text: str) -> list[dict[str, Any]]:
    """Return the locatable blocks of ``(kind, index, text)`` *entries*.

    Args:
        entries: One ``(kind, index, text)`` per piece, in document order.
        raw_text: The extracted text the offsets are measured on.

    Returns:
        One block per entry with ``kind``, ``index``, ``text``, ``char_offset``
        and ``characters``. An entry with no text keeps its position (``index``)
        and an empty payload: dropping it would silently renumber the document.

    Raises:
        InfrastructureError: If a block is not part of ``raw_text`` — the
            position it would claim is unverifiable, hence not reportable.
    """
    blocks: list[dict[str, Any]] = []
    cursor = 0
    for kind, index, text in entries:
        block_text = text.strip()
        if block_text:
            try:
                offset = raw_text.index(block_text, cursor)
            except ValueError as exc:
                raise InfrastructureError(
                    f"extracted {kind} {index} is not part of the document text"
                ) from exc
            cursor = offset + len(block_text)
        else:
            offset = cursor
        blocks.append(
            {
                "kind": kind,
                "index": index,
                "text": block_text,
                "char_offset": offset,
                "characters": len(block_text),
            }
        )
    return blocks


def _paragraph_entries(text: str) -> list[tuple[str, int, str]]:
    """Return one ``section`` entry per non-empty blank-line separated paragraph."""
    entries: list[tuple[str, int, str]] = []
    for piece in text.split("\n\n"):
        if piece.strip():
            entries.append(("section", len(entries) + 1, piece))
    return entries


def _pdf_entries(path: Path) -> list[tuple[str, int, str]]:
    """Return one ``page`` entry per PDF page, in page order (``pypdf``).

    The text of a page comes from its **text layer**: a scanned page without one
    yields an empty page and is declared as such upstream — INIS V1 has no OCR
    (§9.2) and will not describe a picture it cannot read.
    """
    import pypdf

    reader = pypdf.PdfReader(str(path))
    return [
        ("page", number, page.extract_text() or "")
        for number, page in enumerate(reader.pages, start=1)
    ]


def _docx_entries(path: Path) -> list[tuple[str, int, str]]:
    """Return the ``paragraph`` entries of a DOCX, then one ``table`` entry each.

    ``index`` is the position in ``document.paragraphs`` / ``document.tables``,
    which is what makes the locator checkable against the source document.
    """
    import docx

    document = docx.Document(str(path))
    entries: list[tuple[str, int, str]] = [
        ("paragraph", index, paragraph.text)
        for index, paragraph in enumerate(document.paragraphs, start=1)
    ]
    for index, table in enumerate(document.tables, start=1):
        rows = ["\t".join(cell.text for cell in row.cells) for row in table.rows]
        entries.append(("table", index, _BLOCK_SEPARATOR.join(rows)))
    return entries


def _extraction(file_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(text, blocks)`` of *file_path*, decoded according to its suffix.

    Raises:
        InfrastructureError: For an unsupported suffix, a missing §4.1
            extraction library, or a payload that cannot be decoded. INIS never
            reports an unreadable document as an empty one (§0.2, §25.1).
    """
    suffix = file_path.suffix.lower()

    if suffix in _PLAIN_TEXT_SUFFIXES or suffix in _HTML_SUFFIXES:
        # A UTF-8 BOM is an encoding artefact, not document text: it is dropped
        # so the first block starts where the document does.
        text = file_path.read_text(encoding="utf-8-sig", errors="replace")
        return text, _blocks(_paragraph_entries(text), raw_text=text)

    if suffix == ".pdf":
        try:
            entries = _pdf_entries(file_path)
        except ImportError as exc:  # pragma: no cover - §4.1 pins pypdf
            raise InfrastructureError("pypdf is required to extract PDF text") from exc
        except Exception as exc:
            raise InfrastructureError(f"could not extract PDF text: {exc}") from exc
        text = _BLOCK_SEPARATOR.join(entry[2] for entry in entries)
        return text, _blocks(entries, raw_text=text)

    if suffix == ".docx":
        try:
            entries = _docx_entries(file_path)
        except ImportError as exc:  # pragma: no cover - §4.1 pins python-docx
            raise InfrastructureError("python-docx is required to extract DOCX text") from exc
        except Exception as exc:
            raise InfrastructureError(f"could not extract DOCX text: {exc}") from exc
        text = _BLOCK_SEPARATOR.join(entry[2] for entry in entries)
        return text, _blocks(entries, raw_text=text)

    raise InfrastructureError(f"unsupported document format: {suffix or file_path}")


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
    document = build_document(path, source_id=source_id)
    text, _blocks = _extraction(Path(path))
    return document, text


def extract_document_blocks(
    path: str,
    *,
    source_id: str,
) -> tuple[Document, list[dict[str, Any]]]:
    """Extract the locatable text blocks of *path* with its document envelope.

    A block is the smallest piece of *path* this module can prove the position
    of: one **page** of a PDF, one **paragraph** of a DOCX (then one entry per
    table), one blank-line separated **paragraph** of a plain text or HTML
    payload. ``index`` is the position of that piece in its own document — the
    7th page of the PDF is ``page 7``, the 3rd paragraph of the DOCX is
    ``paragraph 3`` — so a reader can go back to the source and check it.

    Args:
        path: Path of the document.
        source_id: Identifier of the owning source (§0.2).

    Returns:
        ``(document, blocks)`` where each block is
        ``{"kind", "index", "text", "char_offset", "characters"}``. An empty
        page keeps its entry with an empty ``text``: the caller decides what to
        do with it, this module never renumbers a document.

    Raises:
        ValidationError: If the file is missing.
        InfrastructureError: If the §4.1 extraction library is absent or the
            document cannot be decoded.
    """
    document = build_document(path, source_id=source_id)
    _text, blocks = _extraction(Path(path))
    return document, blocks


def extract_document(path: str, *, source_id: str) -> Document:
    """Return the §21 ``Document`` envelope extracted from *path*."""
    document, _text = extract_document_text(path, source_id=source_id)
    return document
