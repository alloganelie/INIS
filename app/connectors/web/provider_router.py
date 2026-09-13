"""Web-search provider router (§10.1).

NOTE — temporary local types: ``app/domain/entities/search_result.py``
(Codex) and ``app/domain/interfaces/search_provider.py`` are still
empty placeholders, so ``SearchResult`` and the ``SearchProvider``
protocol live here. They must converge to the domain contracts as
soon as Codex implements them. Providers import these types from this
module; the router never imports providers (injection only, no cycle).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from typing import runtime_checkable


@dataclass(frozen=True)
class SearchResult:
    """One web-search hit (raw collection level, §10)."""

    title: str
    url: str
    snippet: str = ""
    reliability_score: float = 0.0


@runtime_checkable
class SearchProvider(Protocol):
    """Local copy of the §10.1 SearchProvider contract (see module note)."""

    provider_id: str

    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


class ProviderRouter:
    """Route a search to the configured provider (§10.1)."""

    def __init__(
        self,
        providers: dict[str, SearchProvider] | None = None,
        default_provider_id: str = "mock",
    ) -> None:
        self._providers: dict[str, SearchProvider] = dict(providers or {})
        self._default_provider_id = default_provider_id

    def register(self, provider: SearchProvider) -> None:
        """Register (or replace) a provider by its ``provider_id``."""
        provider_id = getattr(provider, "provider_id", "")
        if not provider_id or not isinstance(provider_id, str):
            raise ValueError("provider must expose a non-empty provider_id")
        if not hasattr(provider, "search") or not callable(provider.search):
            raise ValueError("provider must expose an async search method")
        self._providers[provider_id] = provider

    @property
    def provider_ids(self) -> tuple[str, ...]:
        """Return the sorted ids of registered providers."""
        return tuple(sorted(self._providers))

    def resolve(self, provider_id: str | None = None) -> SearchProvider:
        """Return the provider for ``provider_id`` (or the default)."""
        target = provider_id or self._default_provider_id
        try:
            return self._providers[target]
        except KeyError:
            raise ValueError(
                f"Unknown search provider: {target}. "
                f"Registered: {sorted(self._providers)}"
            ) from None

    async def search(
        self,
        query: str,
        limit: int,
        provider_id: str | None = None,
    ) -> list[SearchResult]:
        """Delegate the search to the resolved provider (§10.1)."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return await self.resolve(provider_id).search(query, limit)
