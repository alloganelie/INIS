"""Classification LLM task per INIS spec §22.3 (classer les informations)."""

from __future__ import annotations

from typing import Any

from app.llm.router.model_router import LLMTask, ModelRouter


class ClassificationTask:
    """Classify information into candidate labels via the router."""

    task_type = "classification"

    def __init__(self, router: ModelRouter | None = None) -> None:
        """Initialize with an optional shared router."""
        self._router = router or ModelRouter()

    async def run(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Execute the classification task and return the result as a dict.

        Args:
            prompt: Classification prompt built by ``classification_prompt``.
            **kwargs: Forwarded to ``ModelRouter.complete`` (e.g. ``client``).

        Returns:
            Dict with task_type, model, content, usage and stub flag.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        response = await self._router.complete(
            LLMTask(task_type=self.task_type), prompt, **kwargs
        )
        return {
            "task_type": self.task_type,
            "model": response.model,
            "content": response.content,
            "stub": response.stub,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
        }
