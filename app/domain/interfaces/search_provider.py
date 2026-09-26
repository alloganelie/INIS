"""Search provider contract used by INIS planning (§10.1).

This module is the **single source of truth** for the ``SearchProvider``
protocol: the web provider router and every concrete provider (Serper, Brave,
Wikipedia, mock) must conform to this contract instead of declaring a local
copy. Providers import ``SearchResult`` from here or from the router, which
re-exports it.
"""

from typing import Protocol
from typing import runtime_checkable

from app.domain.entities import SearchResult


@runtime_checkable
class SearchProvider(Protocol):
    """A provider capable of returning ranked search results."""

    provider_id: str

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Return at most *limit* results for *query*."""

