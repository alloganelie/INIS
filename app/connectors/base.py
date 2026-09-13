"""Base connector protocol for INIS source connectors per §9."""

from dataclasses import dataclass
from typing import Optional, Protocol, Union


@dataclass
class Query:
    """Query for source discovery."""

    query_string: str
    filters: Optional[dict[str, str]] = None


@dataclass
class SourceCandidate:
    """A candidate source discovered by a connector."""

    source_id: str
    location: str
    metadata: dict[str, str]


@dataclass
class RawSource:
    """Raw data retrieved from a source."""

    source_id: str
    data: Union[bytes, str]
    content_type: str
    metadata: dict[str, str]


@dataclass
class SourceMetadata:
    """Metadata about a source."""

    source_id: str
    size_bytes: int
    record_count: Optional[int] = None
    schema: Optional[dict[str, str]] = None
    last_modified: Optional[str] = None


@dataclass
class HealthStatus:
    """Health status of a connector."""

    healthy: bool
    message: str
    latency_ms: Optional[float] = None


@dataclass
class ConnectorMetadata:
    """Metadata about a connector."""

    connector_id: str
    name: str
    version: str
    supported_source_types: list[str]


class SourceConnector(Protocol):
    """Protocol for source connectors per §9."""

    connector_id: str
    supported_source_types: list[str]

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover sources matching the query."""
        ...

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw data from a candidate source."""
        ...

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw data to extract metadata."""
        ...

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy."""
        ...

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata."""
        ...
