"""Construction of INIS plans from selected execution steps."""

from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.ulid import ULID


class PlanBuilder:
    """Build the plan structure defined in INIS section 8.2."""

    def build(
        self,
        request_id: str,
        objective: str,
        steps: list[dict[str, Any]],
        budget: dict[str, int | float | None],
    ) -> dict[str, Any]:
        """Return a complete plan with generated plan and step identifiers."""
        return {
            "plan_id": ULID.new("PLAN_"),
            "request_id": request_id,
            "objective": objective,
            "steps": [
                self._build_step(step, order)
                for order, step in enumerate(steps, start=1)
            ],
            "budget": {
                "max_iterations": budget["max_iterations"],
                "max_cost": budget["max_cost"],
                "max_execution_time_seconds": budget["max_execution_time_seconds"],
            },
            "created_at": datetime.now(UTC).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
        }

    @staticmethod
    def _build_step(step: dict[str, Any], order: int) -> dict[str, Any]:
        """Normalize a selected step to the section 8.2 delivery structure."""
        return {
            "step_id": ULID.new("STEP_"),
            "order": order,
            "action": step["action"],
            "tool": step["tool"],
            "inputs": step.get("inputs", {}),
            "expected_output": step["expected_output"],
            "status": step.get("status", "pending"),
            "depends_on": step.get("depends_on", []),
        }
