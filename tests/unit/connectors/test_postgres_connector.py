"""Tests for the PostgreSQL connector: no fabricated data, bound SQL, write support."""

from __future__ import annotations

from typing import Any, Self

import pytest

from app.connectors.base import Query, RawSource, SourceCandidate
from app.connectors.database.postgres_connector import PostgresConnector
from app.core.errors import InfrastructureError, ValidationError


class FakeResult:
    """Minimal SQLAlchemy result surface (rows, keys, rowcount)."""

    def __init__(
        self,
        rows: list[Any] | None = None,
        keys: tuple[str, ...] = (),
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self._keys = keys
        self.rowcount = rowcount

    def fetchall(self) -> list[Any]:
        return self._rows

    def keys(self) -> tuple[str, ...]:
        return self._keys


class FakeConnection:
    """Async connection recording every statement and its parameters."""

    def __init__(self, result: FakeResult) -> None:
        self._result = result
        self.executions: list[tuple[str, Any]] = []
        self.transaction_started = False

    async def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        self.executions.append((str(statement), parameters))
        return self._result

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeEngine:
    """Async engine double exposing connect() and begin()."""

    def __init__(self, result: FakeResult) -> None:
        self.connection = FakeConnection(result)

    def connect(self) -> FakeConnection:
        return self.connection

    def begin(self) -> FakeConnection:
        self.connection.transaction_started = True
        return self.connection


def _connector(engine: FakeEngine | None = None, **kwargs: Any) -> PostgresConnector:
    """Build a connector bound to a fake engine (or to an unusable URL)."""
    connector = PostgresConnector(
        "postgresql+asyncpg://user:secret@localhost:5432/inis" if engine else "not-a-url",
        **kwargs,
    )
    if engine is not None:
        connector._engine = engine  # type: ignore[assignment]
    return connector


def test_constructor_rejects_invalid_configuration() -> None:
    """An empty URL or a non-positive row bound is a programming error."""
    with pytest.raises(ValidationError):
        PostgresConnector("")
    with pytest.raises(ValidationError):
        PostgresConnector("postgresql+asyncpg://localhost/inis", max_rows=0)


async def test_unusable_connection_string_raises_infrastructure_error() -> None:
    """A connector that cannot reach its database fails instead of degrading."""
    connector = PostgresConnector("not-a-url")

    with pytest.raises(InfrastructureError, match="unavailable"):
        await connector.discover(Query(query_string="agents"))


async def test_discover_returns_only_real_tables() -> None:
    """Discovered candidates mirror the information_schema rows, never more."""
    engine = FakeEngine(FakeResult(rows=[("agents",), ("information_units",)]))
    connector = _connector(engine)

    candidates = await connector.discover(Query(query_string="a"))

    statement, parameters = engine.connection.executions[0]
    assert "information_schema.tables" in statement
    assert parameters == {"pattern": "%a%"}
    assert [candidate.metadata["table"] for candidate in candidates] == [
        "agents",
        "information_units",
    ]
    assert all(candidate.source_id.startswith("postgres-") for candidate in candidates)


async def test_discover_never_fabricates_a_candidate() -> None:
    """No matching table means an empty list — not a plausible fake source (§0.2)."""
    engine = FakeEngine(FakeResult(rows=[]))
    connector = _connector(engine)

    assert await connector.discover(Query(query_string="does-not-exist")) == []


async def test_retrieve_binds_the_limit_and_returns_rows_as_text() -> None:
    """Only the validated identifier is interpolated; LIMIT travels as a bind."""
    engine = FakeEngine(FakeResult(rows=[("REQ_01", "agents")], keys=("col_a", "col_b")))
    connector = _connector(engine, max_rows=25)
    candidate = SourceCandidate(
        source_id="postgres-agents",
        location="postgresql://localhost/inis",
        metadata={"type": "postgresql", "table": "agents"},
    )

    raw = await connector.retrieve(candidate)

    statement, parameters = engine.connection.executions[0]
    assert statement == "SELECT * FROM agents LIMIT :limit"
    assert parameters == {"limit": 25}
    assert raw.source_id == "postgres-agents"
    assert raw.content_type == "text/plain"
    assert "'col_a': 'REQ_01', 'col_b': 'agents'" in raw.data


async def test_retrieve_rejects_unsafe_identifiers_and_limits() -> None:
    """A candidate that cannot be safely interpolated is refused, not degraded."""
    engine = FakeEngine(FakeResult(rows=[]))
    connector = _connector(engine)
    injected = SourceCandidate(
        source_id="postgres-x",
        location="postgresql://localhost/inis",
        metadata={"type": "postgresql", "table": "agents; DROP TABLE agents"},
    )
    invalid_limit = SourceCandidate(
        source_id="postgres-agents",
        location="postgresql://localhost/inis",
        metadata={"type": "postgresql", "table": "agents", "limit": "0"},
    )

    with pytest.raises(ValidationError, match="identifier"):
        await connector.retrieve(injected)
    with pytest.raises(ValidationError, match="limit"):
        await connector.retrieve(invalid_limit)
    assert engine.connection.executions == []


async def test_write_inserts_rows_with_bound_parameters() -> None:
    """write() runs one parameterised INSERT inside a transaction."""
    engine = FakeEngine(FakeResult(rowcount=2))
    connector = _connector(engine)

    written = await connector.write(
        "agents",
        [{"agent_id": "AG_01", "name": "planner"}, {"agent_id": "AG_02", "name": "executor"}],
    )

    statement, parameters = engine.connection.executions[0]
    assert statement == "INSERT INTO agents (agent_id, name) VALUES (:agent_id, :name)"
    assert parameters == [
        {"agent_id": "AG_01", "name": "planner"},
        {"agent_id": "AG_02", "name": "executor"},
    ]
    assert engine.connection.transaction_started is True
    assert written == 2


async def test_write_validates_table_columns_and_rows() -> None:
    """Invalid identifiers, heterogeneous rows and empty input are refused."""
    connector = _connector(FakeEngine(FakeResult(rowcount=1)))

    with pytest.raises(ValidationError, match="rows must not be empty"):
        await connector.write("agents", [])
    with pytest.raises(ValidationError, match="identifier"):
        await connector.write("agents; DROP TABLE agents", [{"agent_id": "AG_01"}])
    with pytest.raises(ValidationError, match="identifier"):
        await connector.write("agents", [{"agent-id": "AG_01"}])
    with pytest.raises(ValidationError, match="same columns"):
        await connector.write("agents", [{"agent_id": "AG_01"}, {"name": "planner"}])


async def test_health_check_reports_an_unreachable_database() -> None:
    """The connector never claims to be healthy when it cannot be used."""
    status = await PostgresConnector("not-a-url").health_check()

    assert status.healthy is False
    assert "unhealthy" in status.message
    assert status.latency_ms is not None


async def test_inspect_counts_records_for_text_and_bytes() -> None:
    """inspect() works on both text and binary payloads."""
    connector = _connector(FakeEngine(FakeResult()))
    text_raw = RawSource(
        source_id="postgres-agents",
        data="row-1\nrow-2\n",
        content_type="text/plain",
        metadata={},
    )
    bytes_raw = RawSource(
        source_id="postgres-agents",
        data=b"row-1\nrow-2\n",
        content_type="text/plain",
        metadata={},
    )

    text_metadata = await connector.inspect(text_raw)
    bytes_metadata = await connector.inspect(bytes_raw)

    assert text_metadata.record_count == 2
    assert bytes_metadata.record_count == 2
    assert bytes_metadata.size_bytes == len(b"row-1\nrow-2\n")
