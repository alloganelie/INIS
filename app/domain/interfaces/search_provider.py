"""Search provider contract used by INIS planning."""

from typing import Protocol

from app.domain.entities import SearchResult


class SearchProvider(Protocol):
    """A provider capable of returning ranked search results."""

    provider_id: str

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Return at most *limit* results for *query*."""
