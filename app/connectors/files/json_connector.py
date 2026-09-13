"""JSON connector for INIS per §9.1."""

import json
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


class JSONConnector:
    """JSON file connector using stdlib json module."""

    connector_id: str = "json-connector"
    supported_source_types: list[str] = ["json"]

    def __init__(self, base_path: str = ".") -> None:
        """Initialize the JSON connector.

        Args:
            base_path: Base directory for JSON file discovery.
        """
        self._base_path = Path(base_path)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover JSON files matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
        candidates: list[SourceCandidate] = []
        for json_file in self._base_path.glob("*.json"):
            if query.query_string.lower() in json_file.name.lower():
                candidates.append(
                    SourceCandidate(
                        source_id=f"json-{json_file.stem}",
                        location=str(json_file),
                        metadata={"filename": json_file.name},
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw JSON data from a candidate.

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
            content_type="application/json",
            metadata=candidate.metadata,
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw JSON data to extract metadata.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        if isinstance(raw.data, str):
            try:
                data = json.loads(raw.data)
                if isinstance(data, list):
                    record_count = len(data)
                    schema = {}
                    if data:
                        first_item = data[0]
                        if isinstance(first_item, dict):
                            schema = {k: type(v).__name__ for k, v in first_item.items()}
                elif isinstance(data, dict):
                    record_count = 1
                    schema = {k: type(v).__name__ for k, v in data.items()}
                else:
                    record_count = 1
                    schema = {"value": type(data).__name__}

                return SourceMetadata(
                    source_id=raw.source_id,
                    size_bytes=len(raw.data.encode("utf-8")),
                    record_count=record_count,
                    schema=schema,
                )
            except json.JSONDecodeError:
                return SourceMetadata(
                    source_id=raw.source_id,
                    size_bytes=len(raw.data.encode("utf-8")),
                    record_count=0,
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
        return HealthStatus(healthy=True, message="JSON connector healthy")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="JSON Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
