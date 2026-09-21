"""Add caller context while keeping the request in memory by default."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.agents.understanding.request_parser import InformationRequest


class ContextEnrichmentModel(Protocol):
    """Optional model boundary; concrete LLM modules remain optional."""

    def enrich(self, objective: str, context: dict[str, Any]) -> dict[str, Any]:
        """Return supplemental context for the supplied objective."""


@dataclass(frozen=True)
class ContextEnrichmentResult:
    """Enriched context and an explicit signal when no optional model is configured."""

    context: dict[str, Any]
    model_enrichment_skipped: bool


class ContextEnricher:
    """Merge trusted supplied context and optionally invoke an injected model boundary."""

    def __init__(self, model: ContextEnrichmentModel | None = None) -> None:
        self._model = model

    def enrich(
        self,
        request: InformationRequest,
        additional_context: dict[str, Any] | None = None,
    ) -> ContextEnrichmentResult:
        """Return context without importing an optional ``app.llm`` implementation."""
        context = dict(request.context)
        context.update(additional_context or {})
        if self._model is None:
            return ContextEnrichmentResult(context=context, model_enrichment_skipped=True)
        context.update(self._model.enrich(request.objective, dict(context)))
        return ContextEnrichmentResult(context=context, model_enrichment_skipped=False)
