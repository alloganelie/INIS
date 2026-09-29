"""Content-based document type detection (§9.1, §36.6).

An uploaded file must be identified by **what it contains**, never by what the
client called it: a ``.csv`` extension on a ZIP archive, a ``.txt`` on a PDF, or
a name crafted to escape the storage prefix must all be detected from the bytes.
The client-supplied name is only used as a hint for the two formats whose content
cannot prove anything (markdown versus plain text).

The whitelist is deliberately closed (§25.2): a type that is not listed is
*refused with its detected type named*, never stored as an opaque blob the
ingestion path could not read later.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

from defusedxml import ElementTree

from app.core.errors import ValidationError

__all__ = [
    "EXTENSIONS",
    "SUPPORTED_MIME_TYPES",
    "SniffedDocument",
    "require_supported",
    "sniff_mime_type",
    "supported_types_message",
]

#: MIME type → extension written in the storage key and the stored file name.
EXTENSIONS: dict[str, str] = {
    "text/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}

#: The §9.1 file types INIS accepts today (closed list).
SUPPORTED_MIME_TYPES: frozenset[str] = frozenset(EXTENSIONS)

#: Types a sniffer can recognise but that the pipeline cannot read yet.
_KNOWN_UNSUPPORTED: dict[str, str] = {
    "application/zip": "archive ZIP",
    "image/jpeg": "image JPEG",
    "image/png": "image PNG",
    "application/octet-stream": "binaire non identifié",
}

#: Office Open XML member that identifies a workbook.
_XLSX_MEMBER = "xl/workbook.xml"

#: Office Open XML member that identifies a Word document.
_DOCX_MEMBER = "word/document.xml"

#: Characters kept in a stored file name (the rest is replaced by ``_``).
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class SniffedDocument:
    """What the bytes proved about an uploaded document."""

    mime_type: str
    extension: str
    supported: bool
    evidence: str

    def safe_file_name(self, client_name: str | None, *, fallback_stem: str) -> str:
        """Return a stored file name that cannot escape its storage prefix.

        The *detected* extension wins over the client's: the stored name must
        describe the bytes that were actually written (§18.1).
        """
        stem = (client_name or "").replace("\\", "/").split("/")[-1]
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem
        cleaned = _UNSAFE_NAME_CHARS.sub("_", stem).strip("._") or fallback_stem
        return f"{cleaned}{self.extension}"


def _is_zip(data: bytes) -> bool:
    """Return whether *data* starts with a ZIP signature."""
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _ooxml_type(data: bytes) -> tuple[str, str] | None:
    """Return ``(mime_type, evidence)`` of a ZIP payload, or ``None``."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return None
    if _XLSX_MEMBER in names:
        return (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"archive ZIP contenant {_XLSX_MEMBER}",
        )
    if _DOCX_MEMBER in names:
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"archive ZIP contenant {_DOCX_MEMBER}",
        )
    return None


def _is_parseable_json(text: str) -> bool:
    """Return whether *text* is a complete JSON document."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except (ValueError, TypeError):
        return False
    return True


def _is_parseable_xml(text: str) -> bool:
    """Return whether *text* is a complete XML document."""
    stripped = text.strip()
    if not stripped.startswith("<"):
        return False
    try:
        ElementTree.fromstring(stripped)
    except Exception:  # noqa: BLE001 - any parse failure means "not XML"
        return False
    return True


def _csv_columns(line: str) -> int:
    """Return the number of columns of a CSV line, ``0`` when ambiguous."""
    for delimiter in (";", ",", "\t", "|"):
        if delimiter in line:
            return len(line.split(delimiter))
    return 0


def _looks_like_csv(text: str) -> bool:
    """Return whether *text* looks like a table with at least one data row.

    A single column of prose is not a CSV: at least two lines sharing the same
    number of delimited fields are required, which is what a table header plus
    rows looks like.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    header = _csv_columns(lines[0])
    if header < 2:
        return False
    return all(_csv_columns(line) == header for line in lines[1:4])


def _decode_text(data: bytes) -> str | None:
    """Return *data* as text, or ``None`` when it is not valid UTF-8 text."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    # A NUL byte is the signature of a binary payload that happens to decode.
    if "\x00" in text:
        return None
    return text


def sniff_mime_type(data: bytes, client_name: str | None = None) -> SniffedDocument:
    """Return the type of *data*, proved by its content when possible.

    Args:
        data: The uploaded bytes (may be empty).
        client_name: The client-supplied file name, used only to tell markdown
            from plain text (no content signature distinguishes them).

    Returns:
        The :class:`SniffedDocument`; ``supported`` says whether §9.1 accepts it.
    """
    if data.startswith(b"%PDF-"):
        mime, evidence = "application/pdf", "signature %PDF-"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime, evidence = "image/png", "signature PNG"
    elif data.startswith(b"\xff\xd8\xff"):
        mime, evidence = "image/jpeg", "signature JPEG"
    elif _is_zip(data):
        ooxml = _ooxml_type(data)
        mime, evidence = ooxml if ooxml is not None else (
            "application/zip",
            "signature ZIP sans membre Office Open XML",
        )
    else:
        text = _decode_text(data)
        if text is None:
            mime = "application/octet-stream"
            evidence = "aucune signature connue, contenu binaire"
        elif _is_parseable_json(text):
            mime, evidence = "application/json", "document JSON analysable"
        elif _is_parseable_xml(text):
            mime, evidence = "application/xml", "document XML analysable"
        elif _looks_like_csv(text):
            mime, evidence = "text/csv", "table délimitée cohérente (en-tête + lignes)"
        elif (client_name or "").lower().endswith((".md", ".markdown")):
            mime, evidence = "text/markdown", "texte UTF-8, indication client .md"
        else:
            mime, evidence = "text/plain", "texte UTF-8 sans structure reconnue"

    return SniffedDocument(
        mime_type=mime,
        extension=EXTENSIONS.get(mime, ""),
        supported=mime in SUPPORTED_MIME_TYPES,
        evidence=evidence,
    )


def supported_types_message() -> str:
    """Return the list of accepted types, for a §25.2 refusal message."""
    return ", ".join(sorted(SUPPORTED_MIME_TYPES))


def require_supported(data: bytes, client_name: str | None = None) -> SniffedDocument:
    """Return the type of *data*, or refuse it explicitly (§25.2, §37).

    Raises:
        ValidationError: When the detected type is not on the §9.1 whitelist,
            naming the detected type and the accepted ones. A type that is
            recognised but not readable (ZIP archive, image) is reported as such
            rather than as an anonymous blob.
    """
    sniffed = sniff_mime_type(data, client_name)
    if sniffed.supported:
        return sniffed

    label = _KNOWN_UNSUPPORTED.get(sniffed.mime_type)
    detected = f"{sniffed.mime_type} ({label})" if label else sniffed.mime_type
    raise ValidationError(
        f"Type de document non supporté : {detected} — preuve : {sniffed.evidence}. "
        f"Types acceptés (§9.1) : {supported_types_message()}."
    )
