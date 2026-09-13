"""Tests for in-memory and persistent audit writing."""

import asyncio

from app.governance.audit.audit_writer import AuditWriter


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


def event() -> dict:
    return {
        "actor_type": "agent",
        "actor_id": "agent-1",
        "action": "search",
        "resource_type": "source",
        "resource_id": "SRC_01H00000000000000000000000",
        "request_id": "REQ_01H00000000000000000000000",
        "result": "success",
        "reason": "completed",
    }


def test_audit_writer_retains_in_memory_behavior_without_engine() -> None:
    async def write_and_list() -> list[dict]:
        writer = AuditWriter()
        await writer.write(event())
        return await writer.list_events("agent-1")

    events = asyncio.run(write_and_list())

    assert len(events) == 1
    assert events[0]["audit_event_id"].startswith("AUD_")


def test_audit_writer_persists_with_mock_engine() -> None:
    async def write() -> FakeConnection:
        connection = FakeConnection()
        writer = AuditWriter(FakeEngine(connection))  # type: ignore[arg-type]
        await writer.write(event())
        return connection

    connection = asyncio.run(write())

    assert len(connection.executions) == 1
    assert connection.executions[0][1]["id"].startswith("AUD_")
    assert connection.executions[0][1]["before_hash"] is None
    assert connection.executions[0][1]["after_hash"] is None


def test_audit_writer_lists_persisted_events_with_mock_engine() -> None:
    async def list_events() -> list[dict]:
        connection = FakeConnection(
            FakeResult(
                [
                    {
                        "audit_event_id": "AUD_01H00000000000000000000000",
                        "actor_id": "agent-1",
                        "action": "search",
                    }
                ]
            )
        )
        return await AuditWriter.list_events_from_db(FakeEngine(connection), "agent-1")  # type: ignore[arg-type]

    assert asyncio.run(list_events()) == [
        {
            "audit_event_id": "AUD_01H00000000000000000000000",
            "actor_id": "agent-1",
            "action": "search",
        }
    ]
