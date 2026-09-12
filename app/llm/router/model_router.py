"""Model Router for LLM selection per INIS spec §22."""

from typing import Optional


class ModelRouter:
    """Routes LLM requests to appropriate models based on task requirements.

    Decision criteria per §22.2:
    - task nature
    - cost budget
    - latency budget
    - context size
    - reasoning capability
    - multimodality
    - availability

    This is an interface layer; no actual LLM calls are made here.
    """

    def __init__(self) -> None:
        """Initialize the model router with default decision table."""
        self._decision_table = {
            "reasoning": "gpt-4",
            "classification": "gpt-3.5-turbo",
            "extraction": "gpt-3.5-turbo",
            "planning": "gpt-4",
            "default": "gpt-3.5-turbo",
        }

    def route(
        self,
        task_type: str,
        cost_budget: Optional[float] = None,
        latency_budget: Optional[float] = None,
    ) -> str:
        """Select appropriate model based on task requirements.

        Args:
            task_type: Type of task (e.g., "reasoning", "classification", "extraction").
            cost_budget: Maximum cost per request (optional).
            latency_budget: Maximum latency in seconds (optional).

        Returns:
            Model identifier string.

        Raises:
            ValueError: If task_type is not recognized.
        """
        if task_type not in self._decision_table:
            raise ValueError(f"Unknown task type: {task_type}")

        # Simple decision logic based on cost and latency budgets
        if cost_budget is not None and cost_budget < 0.01:
            return "gpt-3.5-turbo"

        if latency_budget is not None and latency_budget < 1.0:
            return "gpt-3.5-turbo"

        return self._decision_table[task_type]

    def register_model(self, task_type: str, model_id: str) -> None:
        """Register a model for a specific task type.

        Args:
            task_type: Type of task.
            model_id: Model identifier.
        """
        self._decision_table[task_type] = model_id
