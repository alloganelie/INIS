"""Tests for in-memory and persistent resource lineage tracking."""

import asyncio

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
