"""In-memory tracking of execution budgets."""

from time import monotonic


class BudgetTracker:
    """Track iteration, cost, and elapsed-time limits for one execution."""

    def __init__(
        self,
        max_iterations: int,
        max_cost: float | None,
        max_execution_time_seconds: int,
    ) -> None:
        self.max_iterations = max_iterations
        self.max_cost = max_cost
        self.max_execution_time_seconds = max_execution_time_seconds
        self.iterations = 0
        self.cost = 0.0
        self._started_at = monotonic()

    def can_continue(self) -> bool:
        """Return whether no configured budget has been exhausted."""
        has_iteration_budget = self.iterations < self.max_iterations
        has_cost_budget = self.max_cost is None or self.cost < self.max_cost
        has_time_budget = monotonic() - self._started_at < self.max_execution_time_seconds
        return has_iteration_budget and has_cost_budget and has_time_budget

    def consume_iteration(self) -> None:
        """Record one completed execution iteration."""
        self.iterations += 1

    def consume_cost(self, amount: float) -> None:
        """Record an execution cost amount."""
        self.cost += amount
