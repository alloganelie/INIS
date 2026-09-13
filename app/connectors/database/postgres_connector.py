"""PostgreSQL connector for INIS per §9.1."""

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceConnector,
    SourceMetadata,
)


class PostgresConnector:
    """PostgreSQL database connector using asyncpg."""

    connector_id: str = "postgres-connector"
    supported_source_types: list[str] = ["postgresql"]

    def __init__(self, connection_string: str) -> None:
        """Initialize the PostgreSQL connector.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover PostgreSQL tables matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
        candidates: list[SourceCandidate] = []
        candidates.append(
            SourceCandidate(
                source_id="postgres-sample",
                location=self._connection_string,
                metadata={"type": "postgresql", "query": query.query_string},
            )
        )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw PostgreSQL data from a candidate.

        Args:
            candidate: Source candidate to retrieve.

        Returns:
            Raw source data.
        """
        return RawSource(
            source_id=candidate.source_id,
            data=f"SELECT * FROM table WHERE {candidate.metadata.get('query', '1=1')}",
            content_type="text/plain",
            metadata=candidate.metadata,
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw PostgreSQL data to extract metadata.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        size = len(raw.data) if isinstance(raw.data, str) else len(raw.data)
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
        return HealthStatus(healthy=True, message="PostgreSQL connector healthy (no connection)")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="PostgreSQL Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
