"""Excel connector for INIS per §9.1 (stub implementation)."""

from pathlib import Path

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceMetadata,
)
from app.connectors.files.explicit_target import (
    TargetSpec,
    explicit_candidate,
    explicit_target,
    read_candidate,
)

CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

#: §9.1 — what this connector reads, and how (§8.2/§11 traceability). Both
#: declared suffixes are accepted: the connector retrieves the bytes, and a
#: legacy ``.xls`` is refused by the reader that inspects it, where the real
#: limitation belongs.
SPEC = TargetSpec(
    kind="excel",
    suffixes=(".xlsx", ".xls"),
    content_type=CONTENT_TYPE,
    binary=True,
)


class ExcelConnector:
    """Excel file connector (stub - openpyxl integration in future)."""

    connector_id: str = "excel-connector"
    supported_source_types: list[str] = ["xlsx", "xls"]

    def __init__(self, base_path: str = ".") -> None:
        """Initialize the Excel connector.

        Args:
            base_path: Base directory for Excel file discovery.
        """
        self._base_path = Path(base_path)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover Excel files matching the query.

        Args:
            query: Query for source discovery; a ``filters["location"]`` names one
                exact file (path or ``s3://bucket/key``), otherwise the base
                directory is globbed (§9.1/C3).

        Returns:
            List of source candidates.

        Raises:
            ValidationError: When an explicit target is not an Excel file.
        """
        target = explicit_target(query)
        if target is not None:
            return [explicit_candidate(target, SPEC)]

        candidates: list[SourceCandidate] = []
        for excel_file in self._base_path.glob("*.xlsx"):
            if query.query_string.lower() in excel_file.name.lower():
                candidates.append(
                    SourceCandidate(
                        source_id=f"excel-{excel_file.stem}",
                        location=str(excel_file),
                        metadata={"filename": excel_file.name},
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw Excel data from a candidate.

        Args:
            candidate: Source candidate to retrieve.

        Returns:
            Raw source data, whose ``metadata`` carries the ``content_type`` and
            the ``location`` it was read from (§11).

        Raises:
            FileNotFoundError: When the file does not exist.
            InfrastructureError: When the object storage is not configured for an
                ``s3://`` target.
            ValidationError: When the source exceeds ``[limits].max_upload_bytes``.
        """
        return read_candidate(candidate, SPEC)

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw Excel data to extract metadata.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        size = len(raw.data) if isinstance(raw.data, bytes) else len(raw.data.encode("utf-8"))
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=size,
            record_count=None,
            schema=None,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy.

        Returns:
            Health status.
        """
        return HealthStatus(healthy=True, message="Excel connector healthy (stub)")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="Excel Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
