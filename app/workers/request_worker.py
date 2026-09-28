"""Request worker: executes queued information requests (§8, §28).

The worker is a thin scheduling boundary. It owns no business logic: every
request is delegated to the pipeline runner, which remains the single place
where findings, evidence and confidence are produced (§0.2, §22.3). This keeps
the worker safe to call from an AMQP consumer or a local scheduler.
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any
from typing import Protocol

from app.core.errors import ValidationError

__all__ = ["PipelineRunnerLike", "RequestWorker"]


class PipelineRunnerLike(Protocol):
    """Minimal runner surface required by :class:`RequestWorker` (§24)."""

    async def run(self, request_id: str, payload: Any) -> dict[str, Any]: ...


class RequestWorker:
    """Execute information requests by delegating to a pipeline runner."""

    def __init__(self, runner: PipelineRunnerLike | None = None) -> None:
        """Initialise the worker.

        Args:
            runner: Runner used to execute requests. When omitted, the
                process-wide ``pipeline_runner`` singleton is imported lazily
                so this module never creates an import cycle with the API
                layer.
        """
        if runner is None:
            from app.api.v1.requests.pipeline_runner import pipeline_runner

            runner = pipeline_runner
        self._runner = runner

    @property
    def runner(self) -> PipelineRunnerLike:
        """Return the runner this worker delegates to."""
        return self._runner

    async def process(self, request_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Execute one request and return its §24.1 delivery response.

        Args:
            request_id: Identifier of the request being processed.
            payload: Request payload as received by the API layer.

        Returns:
            The delivery response produced by the runner.

        Raises:
            ValidationError: If *request_id* is empty.
        """
        if not request_id or not isinstance(request_id, str):
            raise ValidationError("request_id must be a non-empty string")
        return await self._runner.run(request_id, dict(payload))

    async def process_batch(
        self, requests: Sequence[tuple[str, Mapping[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Execute requests sequentially, preserving the input order.

        Args:
            requests: Ordered ``(request_id, payload)`` pairs.

        Returns:
            One delivery response per input request, in the same order.
        """
        return [await self.process(request_id, payload) for request_id, payload in requests]

