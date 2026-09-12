"""Cost Tracker for LLM usage per INIS spec §22."""

from collections import defaultdict


class CostTracker:
    """Tracks LLM costs by model for budget management per §38."""

    def __init__(self) -> None:
        """Initialize the cost tracker."""
        self._costs: dict[str, float] = defaultdict(float)

    def record_cost(self, model_id: str, cost: float) -> None:
        """Record a cost for a specific model.

        Args:
            model_id: Model identifier.
            cost: Cost in USD.
        """
        if cost < 0:
            raise ValueError("Cost cannot be negative")
        self._costs[model_id] += cost

    def get_total_cost(self, model_id: str) -> float:
        """Get total cost for a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            Total cost in USD.
        """
        return self._costs[model_id]

    def get_all_costs(self) -> dict[str, float]:
        """Get all recorded costs by model.

        Returns:
            Dictionary mapping model IDs to total costs.
        """
        return dict(self._costs)

    def reset(self) -> None:
        """Reset all cost tracking."""
        self._costs.clear()
