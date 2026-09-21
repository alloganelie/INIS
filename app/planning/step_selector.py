"""Selection of the next executable step from a plan."""

from typing import Any


class StepSelector:
    """Select the next step to execute based on dependencies and status."""

    def select_next(
        self, steps: list[dict[str, Any]], completed_step_ids: set[str]
    ) -> dict[str, Any] | None:
        """Return the next executable step, or None if no step is ready.

        Args:
            steps: All steps in the plan.
            completed_step_ids: Set of step IDs that have completed successfully.

        Returns:
            The next step dictionary, or None if no step is ready for execution.
        """
        executable_steps = self._get_executable_steps(steps, completed_step_ids)
        
        if not executable_steps:
            return None
        
        # Select the step with the lowest order number (earliest in plan)
        executable_steps.sort(key=lambda s: s["order"])
        return executable_steps[0]

    def _get_executable_steps(
        self, steps: list[dict[str, Any]], completed_step_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Return all steps whose dependencies are satisfied and not yet completed."""
        executable = []
        
        for step in steps:
            step_id = step["step_id"]
            
            # Skip if already completed
            if step_id in completed_step_ids:
                continue
            
            # Skip if already running or failed
            if step.get("status") in ("running", "done", "failed"):
                continue
            
            # Check if all dependencies are completed
            dependencies = step.get("depends_on", [])
            if all(dep_id in completed_step_ids for dep_id in dependencies):
                executable.append(step)
        
        return executable

    def has_remaining_steps(
        self, steps: list[dict[str, Any]], completed_step_ids: set[str]
    ) -> bool:
        """Return whether there are any steps remaining to execute."""
        for step in steps:
            if step["step_id"] not in completed_step_ids:
                return True
        return False

    def get_step_by_id(self, steps: list[dict[str, Any]], step_id: str) -> dict[str, Any] | None:
        """Return a step by its ID, or None if not found."""
        for step in steps:
            if step["step_id"] == step_id:
                return step
        return None
