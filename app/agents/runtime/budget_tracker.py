"""In-memory tracking of execution budgets with optional persistence."""

from datetime import UTC, datetime
from time import monotonic
from typing import Any

import json
from sqlalchemy import text


class BudgetTracker:
    """Track iteration, cost, and elapsed-time limits for one execution."""

    def __init__(
        self,
        max_iterations: int,
        max_cost: float | None,
        max_execution_time_seconds: int,
        request_id: str | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.max_cost = max_cost
        self.max_execution_time_seconds = max_execution_time_seconds
        self.request_id = request_id
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

    def get_usage_snapshot(self) -> dict[str, Any]:
        """Return current usage as a dictionary for persistence."""
        return {
            "iterations": self.iterations,
            "cost_usd": self.cost,
            "elapsed_seconds": monotonic() - self._started_at,
            "timestamp": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }

    async def persist_usage(self, engine: Any) -> None:
        """Persist current usage to budget_usage table (table 0005).

        Args:
            engine: SQLAlchemy engine or connection for database access.
                    If None, this method is a no-op (in-memory mode).
        """
        if engine is None or self.request_id is None:
            return

        from app.domain.value_objects.ulid import ULID

        usage = self.get_usage_snapshot()
        
        # Convert to JSONB-compatible format
        usage_json = json.dumps(usage)
        
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO budget_usage (budget_usage_id, request_id, usage, total_cost_usd, recorded_at)
                    VALUES (:budget_usage_id, :request_id, :usage::jsonb, :total_cost_usd, :recorded_at)
                    """
                ),
                {
                    "budget_usage_id": ULID.new("BUDG_"),
                    "request_id": self.request_id,
                    "usage": usage_json,
                    "total_cost_usd": self.cost,
                    "recorded_at": datetime.now(UTC),
                },
            )
