"""PDF connector for INIS per §9.1."""

from pathlib import Path

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceConnector,
    SourceMetadata,
)

CONTENT_TYPE = "application/pdf"


def _read_pdf(data: bytes) -> tuple[int, bool, dict[str, str], int]:
    """Read structure and text stats via pypdf.

    Args:
        data: Raw PDF bytes.

    Returns:
        Tuple of (page count, encrypted flag, doc info, text chars).
    """
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(data))
    info: dict[str, str] = {}
    if reader.metadata is not None:
        for key in ("title", "author", "subject"):
            value = getattr(reader.metadata, key, None)
            if value:
                info[key] = str(value)
    text_chars = 0
    for page in reader.pages:
        try:
            text_chars += len(page.extract_text() or "")
        except Exception:
            continue
    return len(reader.pages), reader.is_encrypted, info, text_chars


def _count_tables(data: bytes) -> int | None:
    """Count tables with pdfplumber when installed, else None."""
    import io

    try:
        import pdfplumber
    except ImportError:
        return None
    total = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            try:
                total += len(page.extract_tables() or [])
            except Exception:
                continue
    return total


class PDFConnector:
    """PDF file connector (pypdf structure+text, pdfplumber tables when present)."""

    connector_id: str = "pdf-connector"
    supported_source_types: list[str] = ["pdf"]

    def __init__(self, base_path: str = ".") -> None:
        """Initialize the PDF connector.

        Args:
            base_path: Base directory for PDF file discovery.
        """
        self._base_path = Path(base_path)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover PDF files matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
        candidates: list[SourceCandidate] = []
        for pdf_file in self._base_path.glob("*.pdf"):
            if query.query_string.lower() in pdf_file.name.lower():
                candidates.append(
                    SourceCandidate(
                        source_id=f"pdf-{pdf_file.stem}",
                        location=str(pdf_file),
                        metadata={"filename": pdf_file.name},
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw PDF bytes from a candidate.

        Args:
            candidate: Source candidate to retrieve.

        Returns:
            Raw source data.
        """
        file_path = Path(candidate.location)
        content = file_path.read_bytes()
        return RawSource(
            source_id=candidate.source_id,
            data=content,
            content_type=CONTENT_TYPE,
            metadata=candidate.metadata,
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw PDF: size, page count, info dict and table count.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata (size-only when pypdf is unavailable).
        """
        payload = raw.data if isinstance(raw.data, bytes) else raw.data.encode("utf-8")
        try:
            pages, encrypted, info, text_chars = _read_pdf(bytes(payload))
        except ImportError:
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=len(payload),
                record_count=0,
            )
        except Exception:
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=len(payload),
                record_count=0,
            )
        schema = {
            "pages": str(pages),
            "encrypted": str(encrypted),
            "text_chars": str(text_chars),
        }
        schema.update(info)
        tables = _count_tables(bytes(payload))
        if tables is not None:
            schema["tables"] = str(tables)
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=len(payload),
            record_count=pages,
            schema=schema,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy (pypdf importable).

        Returns:
            Health status.
        """
        try:
            import pypdf  # noqa: F401
        except ImportError:
            return HealthStatus(healthy=False, message="PDF connector missing pypdf")
        try:
            import pdfplumber  # noqa: F401

            extra = " (+pdfplumber tables)"
        except ImportError:
            extra = " (pypdf only)"
        return HealthStatus(healthy=True, message=f"PDF connector healthy{extra}")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="PDF Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
