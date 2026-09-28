"""Tests for the request worker (§8, §28)."""

import pytest

from app.core.errors import ValidationError
from app.workers.request_worker import RequestWorker


class RecordingRunner:
    """Runner double recording the requests it was asked to execute."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, request_id: str, payload: object) -> dict:
        self.calls.append((request_id, dict(payload)))  # type: ignore[arg-type]
        return {
            "response_id": f"RESP_{request_id}",
            "request_id": request_id,
            "status": "completed",
        }


async def test_request_worker_delegates_to_the_runner() -> None:
    """One request produces exactly one runner call and one response."""
    runner = RecordingRunner()
    worker = RequestWorker(runner)

    response = await worker.process("REQ_1", {"objective": "map approvals"})

    assert runner.calls == [("REQ_1", {"objective": "map approvals"})]
    assert response["request_id"] == "REQ_1"
    assert response["response_id"] == "RESP_REQ_1"


async def test_request_worker_exposes_its_runner() -> None:
    """The runner is reachable for wiring checks by the API layer."""
    runner = RecordingRunner()

    assert RequestWorker(runner).runner is runner


async def test_request_worker_rejects_empty_request_id() -> None:
    """An empty request id is rejected before touching the runner."""
    runner = RecordingRunner()
    worker = RequestWorker(runner)

    with pytest.raises(ValidationError, match="request_id must be a non-empty string"):
        await worker.process("", {})

    assert runner.calls == []


async def test_request_worker_processes_batches_in_order() -> None:
    """A batch preserves the input order and returns one response each."""
    runner = RecordingRunner()
    worker = RequestWorker(runner)

    responses = await worker.process_batch(
        [("REQ_1", {"objective": "a"}), ("REQ_2", {"objective": "b"})]
    )

    assert [response["request_id"] for response in responses] == ["REQ_1", "REQ_2"]
    assert [request_id for request_id, _ in runner.calls] == ["REQ_1", "REQ_2"]


async def test_request_worker_copies_the_payload() -> None:
    """The worker never mutates the payload it received."""
    runner = RecordingRunner()
    worker = RequestWorker(runner)
    payload = {"objective": "immutable"}

    await worker.process("REQ_1", payload)

    assert payload == {"objective": "immutable"}


def test_request_worker_defaults_to_the_pipeline_runner_singleton() -> None:
    """Without an injected runner the worker uses the process-wide runner."""
    from app.api.v1.requests.pipeline_runner import pipeline_runner

    assert RequestWorker().runner is pipeline_runner
