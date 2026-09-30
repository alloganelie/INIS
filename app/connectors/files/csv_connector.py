"""CSV connector for INIS per §9.1."""

import csv
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

CONTENT_TYPE = "text/csv"

#: §9.1 — what this connector reads, and how (§8.2/§11 traceability).
SPEC = TargetSpec(kind="csv", suffixes=(".csv",), content_type=CONTENT_TYPE)


class CSVConnector:
    """CSV file connector using stdlib csv module."""

    connector_id: str = "csv-connector"
    supported_source_types: list[str] = ["csv"]

    def __init__(self, base_path: str = ".") -> None:
        """Initialize the CSV connector.

        Args:
            base_path: Base directory for CSV file discovery.
        """
        self._base_path = Path(base_path)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover CSV files matching the query.

        Args:
            query: Query for source discovery; a ``filters["location"]`` names one
                exact file (path or ``s3://bucket/key``), otherwise the base
                directory is globbed (§9.1/C3).

        Returns:
            List of source candidates.

        Raises:
            ValidationError: When an explicit target is not a ``.csv`` file.
        """
        target = explicit_target(query)
        if target is not None:
            # §9.1/C3 — the requester named one file: an uploaded document or an
            # S3 object is not in the base directory and would be invisible here.
            return [explicit_candidate(target, SPEC)]

        candidates: list[SourceCandidate] = []
        for csv_file in self._base_path.glob("*.csv"):
            if query.query_string.lower() in csv_file.name.lower():
                candidates.append(
                    SourceCandidate(
                        source_id=f"csv-{csv_file.stem}",
                        location=str(csv_file),
                        metadata={"filename": csv_file.name},
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw CSV data from a candidate.

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
        """Inspect raw CSV data to extract metadata.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        if isinstance(raw.data, str):
            lines = raw.data.split("\n")
            reader = csv.reader(lines)
            headers = next(reader, [])
            # Filter out blank lines (rows with no non-empty fields)
            record_count = sum(1 for row in reader if any(field.strip() for field in row))
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=len(raw.data.encode("utf-8")),
                record_count=record_count,
                schema={h: "string" for h in headers},
            )
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=len(raw.data),
            record_count=0,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy.

        Returns:
            Health status.
        """
        return HealthStatus(healthy=True, message="CSV connector healthy")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="CSV Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
