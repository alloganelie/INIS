"""PostgreSQL connector for INIS per §9.1.

Design rules:

* **No fabricated data.** When the async engine cannot be built, every data
  method raises :class:`~app.core.errors.InfrastructureError` instead of
  returning a plausible looking :class:`RawSource`. §0.2 forbids emitting a fact
  that carries no real ``source_id``, and the previous degraded mode returned a
  fake SQL statement that looked like a successful retrieval.
* **Parameterised SQL.** Only *identifiers* (table and column names) are
  interpolated, and they must match ``^[a-zA-Z_][a-zA-Z0-9_]*$``; every value —
  including ``LIMIT`` — travels as a bound parameter.
* **Write support.** :meth:`PostgresConnector.write` inserts rows with bound
  parameters inside one explicit transaction.
"""

import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceMetadata,
)
from app.core.errors import InfrastructureError, ValidationError
from app.storage.database.engine import create_engine

#: PostgreSQL identifiers used without quoting must match this pattern, which is
#: what makes the f-string interpolation of identifiers safe.
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgresConnector:
    """PostgreSQL database connector using asyncpg and SQLAlchemy."""

    connector_id: str = "postgres-connector"
    supported_source_types: ClassVar[list[str]] = ["postgresql"]

    def __init__(self, connection_string: str, *, max_rows: int = 100) -> None:
        """Initialize the PostgreSQL connector.

        Args:
            connection_string: PostgreSQL connection string.
            max_rows: Upper bound applied to every :meth:`retrieve` query.

        Raises:
            ValidationError: If the connection string is empty or *max_rows* < 1.
        """
        if not connection_string or not isinstance(connection_string, str):
            raise ValidationError("connection_string must be a non-empty string")
        if max_rows < 1:
            raise ValidationError("max_rows must be >= 1")
        self._connection_string = connection_string
        self._max_rows = max_rows
        self._engine: AsyncEngine | None = None

    @staticmethod
    def _validate_table_name(table_name: str) -> bool:
        """Validate a PostgreSQL identifier (table or column name).

        Args:
            table_name: Identifier to validate.

        Returns:
            True if valid, False otherwise.
        """
        return bool(isinstance(table_name, str) and _IDENTIFIER_PATTERN.match(table_name))

    def _require_table_name(self, table_name: str) -> str:
        """Return *table_name* when it is a safe identifier.

        Raises:
            ValidationError: If *table_name* cannot be interpolated safely.
        """
        if not self._validate_table_name(table_name):
            raise ValidationError(f"invalid PostgreSQL identifier: {table_name!r}")
        return table_name

    @staticmethod
    def _positive_int(value: Any, *, default: int, name: str) -> int:
        """Coerce an optional positive integer bound (used for ``LIMIT``)."""
        if value is None or value == "":
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be an integer") from exc
        if parsed < 1:
            raise ValidationError(f"{name} must be >= 1")
        return parsed

    async def _get_engine(self) -> AsyncEngine:
        """Get or create the async engine.

        Returns:
            The configured async engine.

        Raises:
            InfrastructureError: If the connection string cannot build an engine;
                no caller ever receives fabricated data instead (§0.2).
        """
        if self._engine is None:
            try:
                self._engine = create_engine(self._connection_string)
            except Exception as exc:
                raise InfrastructureError(f"PostgreSQL connector unavailable: {exc}") from exc
        return self._engine

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover PostgreSQL tables matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            The matching tables; an empty list is a legitimate "no match" answer
            and never a fabricated candidate (§0.2).

        Raises:
            InfrastructureError: If the database engine cannot be built.
        """
        engine = await self._get_engine()
        candidates: list[SourceCandidate] = []

        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name LIKE :pattern"
                ),
                {"pattern": f"%{query.query_string}%"},
            )
            for row in result.fetchall():
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

        Raises:
            ValidationError: If the candidate carries no safe table name or an
                invalid ``limit``.
            InfrastructureError: If the database engine cannot be built.
        """
        table_name = self._require_table_name(str(candidate.metadata.get("table", "")))
        limit = self._positive_int(
            candidate.metadata.get("limit"),
            default=self._max_rows,
            name="limit",
        )
        engine = await self._get_engine()

        async with engine.connect() as conn:
            # Only the validated identifier is interpolated; LIMIT is a bound
            # parameter, so no external value ever reaches the SQL text.
            result = await conn.execute(
                text(f"SELECT * FROM {table_name} LIMIT :limit"),  # nosec: B608
                {"limit": limit},
            )
            rows = result.fetchall()
            columns = result.keys()

        data_str = "\n".join([str(dict(zip(columns, row))) for row in rows])
        return RawSource(
            source_id=candidate.source_id,
            data=data_str,
            content_type="text/plain",
            metadata=candidate.metadata,
        )

    async def write(
        self,
        table_name: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> int:
        """Insert rows into a PostgreSQL table with bound parameters.

        Args:
            table_name: Destination table (validated identifier).
            rows: Rows to insert; every row must expose the same column names.

        Returns:
            Number of rows written.

        Raises:
            ValidationError: If the table or columns are invalid, or *rows* is empty.
            InfrastructureError: If the database engine cannot be built.
        """
        self._require_table_name(table_name)
        if not rows:
            raise ValidationError("rows must not be empty")
        columns = list(rows[0].keys())
        if not columns:
            raise ValidationError("rows must expose at least one column")
        for column in columns:
            self._require_table_name(column)
        for row in rows:
            if list(row.keys()) != columns:
                raise ValidationError("every row must expose the same columns")

        column_list = ", ".join(columns)
        bind_list = ", ".join(f":{column}" for column in columns)
        statement = text(f"INSERT INTO {table_name} ({column_list}) VALUES ({bind_list})")  # nosec: B608
        engine = await self._get_engine()
        async with engine.begin() as conn:
            result = await conn.execute(statement, [dict(row) for row in rows])
        return int(result.rowcount or 0)

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw PostgreSQL data to extract metadata.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        text_data = (
            raw.data.decode("utf-8", errors="replace") if isinstance(raw.data, bytes) else raw.data
        )
        lines = text_data.split("\n")
        record_count = len([line for line in lines if line.strip()])

        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=len(raw.data),
            record_count=record_count,
            schema=None,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy.

        Returns:
            Health status with latency. An unreachable database reports
            ``healthy=False``: the connector never claims to be healthy while it
            cannot actually be used (§0.2).
        """
        start_time = time.perf_counter()
        try:
            engine = await self._get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - health checks report, never raise
            return HealthStatus(
                healthy=False,
                message=f"PostgreSQL connector unhealthy: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        return HealthStatus(
            healthy=True,
            message="PostgreSQL connector healthy",
            latency_ms=(time.perf_counter() - start_time) * 1000,
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
