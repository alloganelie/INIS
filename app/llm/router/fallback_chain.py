"""Fallback Chain for LLM model selection per INIS spec §22."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.errors import InfrastructureError

T = TypeVar("T")


class FallbackChain:
    """Manages ordered list of models for fallback scenarios per §22.2."""

    def __init__(self, initial_models: list[str]) -> None:
        """Initialize the fallback chain with an ordered list of models.

        Args:
            initial_models: Ordered list of model IDs (first is primary).
        """
        if not initial_models:
            raise ValueError("Fallback chain must have at least one model")
        self._chain: list[str] = list(initial_models)

    def get_primary(self) -> str:
        """Get the primary (first) model in the chain.

        Returns:
            Primary model ID.
        """
        return self._chain[0]

    def get_fallback(self, index: int = 1) -> str:
        """Get a fallback model by index.

        Args:
            index: Fallback index (1 = first fallback, 2 = second, etc.).

        Returns:
            Fallback model ID.

        Raises:
            IndexError: If index is out of range.
        """
        return self._chain[index]

    def get_all(self) -> list[str]:
        """Get all models in the fallback chain.

        Returns:
            Ordered list of model IDs.
        """
        return list(self._chain)

    def add_model(self, model_id: str, position: int = -1) -> None:
        """Add a model to the fallback chain.

        Args:
            model_id: Model ID to add.
            position: Position to insert at (-1 = end of chain).
        """
        if position == -1:
            self._chain.append(model_id)
        else:
            self._chain.insert(position, model_id)

    def remove_model(self, model_id: str) -> None:
        """Remove a model from the fallback chain.

        Args:
            model_id: Model ID to remove.

        Raises:
            ValueError: If model is not in chain or would leave chain empty.
        """
        if len(self._chain) == 1:
            raise ValueError("Cannot remove last model from fallback chain")
        self._chain.remove(model_id)

    async def run(self, func: Callable[[str], Awaitable[T]]) -> T:
        """Try the primary model, then each fallback, return first success.

        Args:
            func: Async callable receiving a model ID and returning a result.

        Returns:
            Result of the first successful call.

        Raises:
            InfrastructureError: If every model in the chain fails.
        """
        failures: list[str] = []
        for model_id in self._chain:
            try:
                return await func(model_id)
            except Exception as exc:  # noqa: BLE001 - collected and reported
                failures.append(f"{model_id}: {exc}")
        raise InfrastructureError(
            f"All {len(self._chain)} models in the fallback chain failed: "
            + "; ".join(failures)
        )
