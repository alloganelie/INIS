"""Web-search provider router (§10.1).

``SearchResult`` is imported from the consolidated
``app.domain.entities.search_result`` module (Codex). The
``SearchProvider`` protocol stays local: ``app/domain/interfaces/
search_provider.py`` is still an empty placeholder. Providers import
these types from this module; the router never imports providers
(injection only, no cycle).
"""

from __future__ import annotations

import os
from typing import Protocol
from typing import runtime_checkable

from app.domain.entities.search_result import SearchResult


@runtime_checkable
class SearchProvider(Protocol):
    """Local copy of the §10.1 SearchProvider contract (see module note)."""

    provider_id: str

    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


class ProviderRouter:
    """Route a search to the configured provider (§10.1).

    When no explicit ``providers`` mapping is given, the primary provider
    is auto-selected from the environment: ``SerperProvider`` when
    ``SERPER_API_KEY`` is set, else ``BraveProvider`` when
    ``BRAVE_API_KEY`` is set, else the free ``WikipediaProvider`` fallback.
    Provider modules are imported lazily so this module keeps its
    no-cycle invariant (providers import ``SearchResult`` from here).
    """

    def __init__(
        self,
        providers: dict[str, SearchProvider] | None = None,
        default_provider_id: str | None = None,
    ) -> None:
        if providers is None:
            primary = _auto_select_primary()
            self._providers: dict[str, SearchProvider] = {
                primary.provider_id: primary
            }
            self._default_provider_id = primary.provider_id
        else:
            self._providers = dict(providers)
            self._default_provider_id = default_provider_id or "mock"

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


def _auto_select_primary() -> SearchProvider:
    """Select the primary provider from the environment (lazy imports).

    ``SERPER_API_KEY`` wins, then ``BRAVE_API_KEY``, else the free
    Wikipedia fallback which needs no key.
    """
    if os.environ.get("SERPER_API_KEY"):
        from app.connectors.web.providers.serper_provider import SerperProvider

        return SerperProvider()
    if os.environ.get("BRAVE_API_KEY"):
        from app.connectors.web.providers.brave_provider import BraveProvider

        return BraveProvider()
    from app.connectors.web.providers.wikipedia_provider import WikipediaProvider

    return WikipediaProvider()
