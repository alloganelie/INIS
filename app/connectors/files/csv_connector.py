"""CSV connector for INIS per §9.1."""

import csv
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
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
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
            Raw source data.
        """
        file_path = Path(candidate.location)
        with file_path.open("r", encoding="utf-8") as f:
            content = f.read()
        return RawSource(
            source_id=candidate.source_id,
            data=content,
            content_type="text/csv",
            metadata=candidate.metadata,
        )

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
            record_count = sum(1 for _ in reader)
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
