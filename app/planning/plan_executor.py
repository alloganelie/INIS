"""Execution of plans with dependency resolution and failure handling."""

from typing import Any, Callable

from app.core.errors import InisError
from app.planning.dependency_resolver import DependencyResolver
from app.planning.step_selector import StepSelector


class ExecutionResult:
    """Result of plan execution."""

    def __init__(
        self,
        success: bool,
        completed_steps: list[str],
        failed_steps: list[str],
        outputs: dict[str, Any],
        error: str | None = None,
    ) -> None:
        self.success = success
        self.completed_steps = completed_steps
        self.failed_steps = failed_steps
        self.outputs = outputs
        self.error = error


class PlanExecutor:
    """Execute plans respecting dependencies with fail/retry handling."""

    def __init__(
        self,
        dependency_resolver: DependencyResolver | None = None,
        step_selector: StepSelector | None = None,
    ) -> None:
        self.dependency_resolver = dependency_resolver or DependencyResolver()
        self.step_selector = step_selector or StepSelector()

    async def execute(
        self,
        plan: dict[str, Any],
        step_executor: Callable[[dict[str, Any]], dict[str, Any]],
        max_retries: int = 3,
    ) -> ExecutionResult:
        """Execute a plan respecting step dependencies.

        Args:
            plan: Plan structure per §8.2.
            step_executor: Async function that executes a single step.
            max_retries: Maximum retry attempts for failed steps.

        Returns:
            ExecutionResult with success status and step outcomes.
        """
        steps = plan["steps"]
        completed_step_ids: set[str] = set()
        failed_step_ids: set[str] = set()
        step_outputs: dict[str, Any] = {}
        retry_counts: dict[str, int] = {}

        try:
            # Validate dependencies
            execution_order = self.dependency_resolver.resolve(steps)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                completed_steps=[],
                failed_steps=[],
                outputs={},
                error=f"Dependency resolution failed: {e}",
            )

        # Execute steps in dependency order
        while self.step_selector.has_remaining_steps(steps, completed_step_ids):
            next_step = self.step_selector.select_next(steps, completed_step_ids)
            
            if next_step is None:
                # No executable steps but remaining steps exist = deadlock
                remaining = [s["step_id"] for s in steps if s["step_id"] not in completed_step_ids]
                return ExecutionResult(
                    success=False,
                    completed_steps=list(completed_step_ids),
                    failed_steps=remaining,
                    outputs=step_outputs,
                    error="Deadlock: no executable steps with remaining dependencies",
                )

            step_id = next_step["step_id"]
            
            # Mark step as running
            next_step["status"] = "running"
            
            try:
                # Execute the step
                output = await step_executor(next_step)
                step_outputs[step_id] = output
                
                # Mark step as completed
                next_step["status"] = "done"
                completed_step_ids.add(step_id)
                
            except Exception as e:
                # Handle step failure
                retry_counts[step_id] = retry_counts.get(step_id, 0) + 1
                
                if retry_counts[step_id] >= max_retries:
                    # Max retries exceeded, mark as failed
                    next_step["status"] = "failed"
                    failed_step_ids.add(step_id)
                    
                    # Check if this failure blocks remaining steps
                    if self._is_blocking_failure(step_id, steps, completed_step_ids):
                        return ExecutionResult(
                            success=False,
                            completed_steps=list(completed_step_ids),
                            failed_steps=list(failed_step_ids),
                            outputs=step_outputs,
                            error=f"Step {step_id} failed after {max_retries} retries: {e}",
                        )
                else:
                    # Retry the step
                    next_step["status"] = "pending"
                    continue

        # Check if all steps completed successfully
        all_completed = len(completed_step_ids) == len(steps)
        
        return ExecutionResult(
            success=all_completed and not failed_step_ids,
            completed_steps=list(completed_step_ids),
            failed_steps=list(failed_step_ids),
            outputs=step_outputs,
            error=None if all_completed else f"Some steps failed: {failed_step_ids}",
        )

    def _is_blocking_failure(
        self, failed_step_id: str, steps: list[dict[str, Any]], completed_step_ids: set[str]
    ) -> bool:
        """Check if a failed step blocks remaining steps."""
        for step in steps:
            if step["step_id"] in completed_step_ids:
                continue
            if step["step_id"] == failed_step_id:
                continue
            
            # If any remaining step depends on the failed step, it's blocking
            if failed_step_id in step.get("depends_on", []):
                return True
        
        return False

    def get_execution_progress(
        self, plan: dict[str, Any], completed_step_ids: set[str]
    ) -> dict[str, Any]:
        """Return execution progress statistics."""
        total_steps = len(plan["steps"])
        completed_count = len(completed_step_ids)
        
        return {
            "total_steps": total_steps,
            "completed_steps": completed_count,
            "remaining_steps": total_steps - completed_count,
            "progress_percentage": (completed_count / total_steps * 100) if total_steps > 0 else 0,
        }
