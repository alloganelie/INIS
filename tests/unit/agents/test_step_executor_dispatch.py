"""§25.2/§37 — a step that fails is degraded, never filled with invented output.

``StepExecutor`` applies one plan step through an injected tool boundary. Its
failure contract matters more than its success path: an *unavailable* tool must
produce a ``degraded`` step carrying the reason (the plan is sound, the
dependency is not), a *broken* step must stay ``failed``, and neither may write a
result that was never produced.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.pipeline.step_executor import StepExecutor
from app.core.errors import InfrastructureError, ValidationError


class _Tool:
    """Tool double: returns a fixed result or raises a fixed error."""

    def __init__(self, *, result: Any = None, error: Exception | None = None) -> None:
        self.calls = 0
        self._result = result
        self._error = error

    def execute(self, step: dict[str, Any]) -> dict[str, Any]:
        """Return the configured result, or raise the configured error."""
        self.calls += 1
        if self._error is not None:
            raise self._error
        return {"output": self._result}


def _step(**overrides: Any) -> dict[str, Any]:
    """Return a pending plan step."""
    step = {
        "step_id": "STEP_1",
        "action": "file_ingest",
        "tool": "read_csv",
        "status": "pending",
    }
    step.update(overrides)
    return step


class TestSuccessPath:
    """Unchanged behaviour: an executed step is done, with its result."""

    def test_a_step_is_executed_and_marked_done(self) -> None:
        tool = _Tool(result="contenu réel")

        result = StepExecutor().execute(_step(), tool)

        assert result["status"] == "done"
        assert result["result"] == {"output": "contenu réel"}
        assert "error" not in result
        assert tool.calls == 1

    def test_an_already_done_step_is_not_replayed(self) -> None:
        tool = _Tool(result="should not run")

        result = StepExecutor().execute(_step(status="done"), tool)

        assert result["status"] == "done"
        assert tool.calls == 0

    def test_a_non_pending_step_is_a_contract_error(self) -> None:
        with pytest.raises(ValidationError, match="not pending"):
            StepExecutor().execute(_step(status="running"), _Tool())


class TestFailurePath:
    """§25.2 — degrade what is unavailable, fail what is broken, invent nothing."""

    def test_an_unavailable_tool_degrades_the_step(self) -> None:
        reason = "read_csv attend un chemin local (lot L2.3)"
        tool = _Tool(error=InfrastructureError(reason))

        result = StepExecutor().execute(_step(), tool)

        assert result["status"] == "degraded"
        assert result["error"] == reason
        assert "result" not in result, "a degraded step has no result to report"
        assert "output" not in result, "no output may be invented to fill the hole"

    def test_a_broken_step_fails_with_its_error(self) -> None:
        tool = _Tool(error=ValueError("chemin illisible"))

        result = StepExecutor().execute(_step(), tool)

        assert result["status"] == "failed"
        assert "chemin illisible" in result["error"]
        assert "result" not in result

    def test_the_input_step_is_never_mutated(self) -> None:
        step = _step()

        StepExecutor().execute(step, _Tool(result="x"))

        assert step["status"] == "pending"
