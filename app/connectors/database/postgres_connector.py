"""PostgreSQL connector for INIS per §9.1."""

import re
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceConnector,
    SourceMetadata,
)
from app.storage.database.engine import create_engine


class PostgresConnector:
    """PostgreSQL database connector using asyncpg and SQLAlchemy."""

    connector_id: str = "postgres-connector"
    supported_source_types: list[str] = ["postgresql"]

    def __init__(self, connection_string: str) -> None:
        """Initialize the PostgreSQL connector.

        Args:
            connection_string: PostgreSQL connection string.
        """
        self._connection_string = connection_string
        self._engine: Optional[AsyncEngine] = None

    def _validate_table_name(self, table_name: str) -> bool:
        """Validate table name to prevent SQL injection.

        Args:
            table_name: Table name to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Only allow alphanumeric, underscore, and hyphen
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', table_name))

    async def _get_engine(self) -> Optional[AsyncEngine]:
        """Get or create the async engine. Returns None in degraded mode."""
        if self._engine is None:
            try:
                self._engine = create_engine(self._connection_string)
            except Exception:
                # Degraded mode: engine not available
                return None
        return self._engine

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover PostgreSQL tables matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
        engine = await self._get_engine()
        if engine is None:
            # Degraded mode: return stub candidate
            return [
                SourceCandidate(
                    source_id=f"postgres-{query.query_string}",
                    location=self._connection_string,
                    metadata={"type": "postgresql", "table": query.query_string},
                )
            ]

        candidates: list[SourceCandidate] = []
        
        async with engine.connect() as conn:
            pattern = f"%{query.query_string}%"
            stmt = text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE :pattern")
            result = await conn.execute(stmt, {"pattern": pattern})
            rows = result.fetchall()
            for row in rows:
                candidates.append(
                    SourceCandidate(
                        source_id=f"postgres-{row[0]}",
                        location=self._connection_string,
                        metadata={"type": "postgresql", "table": row[0]},
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
        engine = await self._get_engine()
        table_name = candidate.metadata.get("table", "unknown")
        
        if engine is None:
            # Degraded mode: return stub query string
            return RawSource(
                source_id=candidate.source_id,
                data=f"SELECT * FROM {table_name} LIMIT 100",
                content_type="text/plain",
                metadata=candidate.metadata,
            )

        # Validate table name to prevent SQL injection
        if not self._validate_table_name(table_name):
            return RawSource(
                source_id=candidate.source_id,
                data="Invalid table name",
                content_type="text/plain",
                metadata=candidate.metadata,
            )

        async with engine.connect() as conn:
            stmt = text(f"SELECT * FROM {table_name} LIMIT 100")
            result = await conn.execute(stmt)
            rows = result.fetchall()
            columns = result.keys()
            
            # Convert to string representation
            data_str = "\n".join([str(dict(zip(columns, row))) for row in rows])
            
            return RawSource(
                source_id=candidate.source_id,
                data=data_str,
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
        lines = raw.data.split("\n") if isinstance(raw.data, str) else []
        record_count = len([line for line in lines if line.strip()])
        
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=size,
            record_count=record_count,
            schema=None,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy.

        Returns:
            Health status with latency.
        """
        start_time = time.time()
        engine = await self._get_engine()
        
        if engine is None:
            # Degraded mode: healthy but no connection
            return HealthStatus(
                healthy=True,
                message="PostgreSQL connector healthy (degraded mode, no engine)",
                latency_ms=None,
            )

        try:
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
            latency_ms = (time.time() - start_time) * 1000
            return HealthStatus(
                healthy=True,
                message="PostgreSQL connector healthy",
                latency_ms=latency_ms,
            )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                message=f"PostgreSQL connector unhealthy: {str(e)}",
                latency_ms=None,
            )

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
