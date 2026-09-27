"""Tests for in-memory and persistent resource lineage tracking."""

import asyncio
from datetime import datetime

from app.provenance.lineage_tracker import LineageTracker


class FakeResult:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict]:
        return self._rows


class FakeConnection:
    def __init__(self, result: FakeResult | None = None) -> None:
        self.executions: list[tuple[object, dict | None]] = []
        self._result = result or FakeResult()

    async def execute(self, statement: object, parameters: dict | None = None) -> FakeResult:
        self.executions.append((statement, parameters))
        return self._result


class FakeContext:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def begin(self) -> FakeContext:
        return FakeContext(self._connection)

    def connect(self) -> FakeContext:
        return FakeContext(self._connection)


def test_lineage_tracker_records_direct_relationships() -> None:
    tracker = LineageTracker()
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])

    assert tracker.get_lineage("INF_02")["ancestry"] == ["INF_01"]
    assert tracker.get_lineage("INF_01")["descendants"] == ["INF_02"]


def test_lineage_tracker_returns_transitive_relationships() -> None:
    tracker = LineageTracker()
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])
    tracker.record("TRF_02", ["INF_02"], ["INF_03"])

    assert tracker.get_lineage("INF_03")["ancestry"] == ["INF_01", "INF_02"]
    assert tracker.get_lineage("INF_01")["descendants"] == ["INF_02", "INF_03"]


def test_lineage_tracker_returns_empty_lineage_for_unknown_resource() -> None:
    assert LineageTracker().get_lineage("INF_unknown") == {
        "ancestry": [],
        "descendants": [],
    }


def test_lineage_tracker_persists_records_with_mock_engine() -> None:
    async def persist() -> tuple[FakeConnection, LineageTracker]:
        connection = FakeConnection()
        tracker = LineageTracker(FakeEngine(connection))  # type: ignore[arg-type]
        tracker.record("TRF_01", ["INF_01"], ["INF_02"])
        await asyncio.sleep(0)
        return connection, tracker

    connection, tracker = asyncio.run(persist())

    assert len(connection.executions) == 1
    assert connection.executions[0][1]["transformation_id"] == "TRF_01"
    assert tracker.get_lineage("INF_02")["ancestry"] == ["INF_01"]


def test_lineage_tracker_loads_lineage_from_mock_engine() -> None:
    async def load() -> dict[str, list[str]]:
        connection = FakeConnection(
            FakeResult(
                [
                    {
                        "transformation_id": "TRF_01",
                        "input_ids": ["INF_01"],
                        "output_ids": ["INF_02"],
                    },
                    {
                        "transformation_id": "TRF_02",
                        "input_ids": ["INF_02"],
                        "output_ids": ["INF_03"],
                    },
                ]
            )
        )
        return await LineageTracker.load_from_db(FakeEngine(connection), "INF_03")  # type: ignore[arg-type]

    assert asyncio.run(load()) == {"ancestry": ["INF_01", "INF_02"], "descendants": []}


class FailingConnection(FakeConnection):
    """Connection whose writes always fail (persistence error paths)."""

    async def execute(self, statement: object, parameters: dict | None = None) -> FakeResult:
        self.executions.append((statement, parameters))
        raise RuntimeError("insert failed")


def test_lineage_tracker_without_engine_skips_persistence() -> None:
    """Without an engine the tracker stays in memory and flush() is a no-op."""
    tracker = LineageTracker()
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])

    assert tracker.persistence_enabled is False
    assert tracker.pending_records == 0
    assert asyncio.run(tracker.flush()) == 0
    assert tracker.get_lineage("INF_02")["ancestry"] == ["INF_01"]


def test_flush_persists_records_queued_outside_a_running_loop() -> None:
    """A record created without a loop waits for flush() instead of being lost."""
    connection = FakeConnection()
    tracker = LineageTracker(FakeEngine(connection))  # type: ignore[arg-type]

    tracker.record("TRF_01", ["INF_01"], ["INF_02"])  # no event loop here

    assert tracker.pending_records == 1

    written = asyncio.run(tracker.flush())

    assert written == 1
    assert tracker.pending_records == 0
    assert connection.executions[0][1]["transformation_id"] == "TRF_01"


def test_flush_awaits_background_tasks_then_reports_zero() -> None:
    """flush() drains the scheduled writes and is idempotent."""

    async def persist() -> tuple[FakeConnection, LineageTracker, int, int]:
        connection = FakeConnection()
        tracker = LineageTracker(FakeEngine(connection))  # type: ignore[arg-type]
        tracker.record("TRF_01", ["INF_01"], ["INF_02"])
        first = await tracker.flush()
        second = await tracker.flush()
        return connection, tracker, first, second

    connection, tracker, first, second = asyncio.run(persist())

    assert (first, second) == (1, 0)
    assert len(connection.executions) == 1
    assert tracker.persistence_errors == []


def test_flush_collects_persistence_failures() -> None:
    """A failing write is reported through persistence_errors, never swallowed."""

    async def persist() -> tuple[LineageTracker, int]:
        tracker = LineageTracker(FakeEngine(FailingConnection()))  # type: ignore[arg-type]
        tracker.record("TRF_01", ["INF_01"], ["INF_02"])
        return tracker, await tracker.flush()

    tracker, written = asyncio.run(persist())

    assert written == 0
    assert len(tracker.persistence_errors) == 1
    assert "RuntimeError" in tracker.persistence_errors[0]


def test_background_failure_is_captured_by_done_callback() -> None:
    """A fire-and-forget write that fails is surfaced on the tracker."""

    async def persist() -> LineageTracker:
        tracker = LineageTracker(FakeEngine(FailingConnection()))  # type: ignore[arg-type]
        tracker.record("TRF_01", ["INF_01"], ["INF_02"])
        await asyncio.sleep(0)  # let the background task run and fail
        return tracker

    tracker = asyncio.run(persist())

    assert tracker.persistence_errors
    assert "RuntimeError" in tracker.persistence_errors[0]


def test_aclose_flushes_queued_records() -> None:
    """Shutdown paths can rely on aclose() to persist what is queued."""
    connection = FakeConnection()
    tracker = LineageTracker(FakeEngine(connection))  # type: ignore[arg-type]
    tracker.record("TRF_01", ["INF_01"], ["INF_02"])

    asyncio.run(tracker.aclose())

    assert len(connection.executions) == 1
    assert tracker.pending_records == 0


def test_persistence_record_encodes_jsonb_columns() -> None:
    """JSONB columns are bound as JSON text and the timestamp stays a datetime."""
    record = LineageTracker._persistence_record("TRF_01", ["INF_01"], ["INF_02"])

    assert record["input_ids"] == '["INF_01"]'
    assert record["output_ids"] == '["INF_02"]'
    assert record["parameters"] == "{}"
    assert isinstance(record["timestamp"], datetime)


def test_persist_record_casts_jsonb_parameters() -> None:
    """The INSERT casts bound JSON text so the JSONB columns accept it."""

    async def persist() -> FakeConnection:
        connection = FakeConnection()
        record = LineageTracker._persistence_record("TRF_01", ["INF_01"], ["INF_02"])
        await LineageTracker._persist_record(FakeEngine(connection), record)  # type: ignore[arg-type]
        return connection

    statement = str(asyncio.run(persist()).executions[0][0])

    assert "CAST(:input_ids AS JSONB)" in statement
    assert "CAST(:output_ids AS JSONB)" in statement
    assert "CAST(:parameters AS JSONB)" in statement


def test_load_from_db_decodes_json_text_identifier_columns() -> None:
    """asyncpg may return JSONB as text; lineage must still list the identifiers."""

    async def load() -> dict[str, list[str]]:
        connection = FakeConnection(
            FakeResult(
                [
                    {
                        "transformation_id": "TRF_01",
                        "input_ids": '["INF_01"]',
                        "output_ids": '["INF_02"]',
                    }
                ]
            )
        )
        return await LineageTracker.load_from_db(FakeEngine(connection), "INF_02")  # type: ignore[arg-type]

    assert asyncio.run(load()) == {"ancestry": ["INF_01"], "descendants": []}

