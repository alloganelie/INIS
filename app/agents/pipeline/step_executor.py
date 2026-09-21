"""Execute individual plan steps through an injected tool boundary."""

from copy import deepcopy
from typing import Any, Protocol

from app.core.errors import ValidationError


class StepTool(Protocol):
    """Boundary for a tool selected by planning without importing tool implementations."""

    def execute(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute one normalized plan step and return its output."""


class StepExecutor:
    """Apply one plan step idempotently in memory."""

    def execute(self, step: dict[str, Any], tool: StepTool) -> dict[str, Any]:
        """Run a pending step, preserving already-completed steps on replay."""
        status = step.get("status", "pending")
        if status == "done":
            return deepcopy(step)
        if status != "pending":
            raise ValidationError(f"Step {step.get('step_id', '<unknown>')} is not pending.")

        result = deepcopy(step)
        result["status"] = "running"
        try:
            result["result"] = tool.execute(deepcopy(result))
        except Exception as error:
            result["status"] = "failed"
            result["error"] = str(error)
            return result

        result["status"] = "done"
        return result
