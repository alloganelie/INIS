"""Brave web-search provider (§9.1, stub).

Without an API key the provider fails explicitly instead of issuing
any network call. With a key it performs a real Brave Search API
query (not exercised in unit tests, which use MockProvider).
"""

from __future__ import annotations

import httpx

from app.connectors.web.provider_router import SearchResult
from app.core.errors import InfrastructureError

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveProvider:
    """SearchProvider backed by Brave Search (stub: key required)."""

    provider_id: str = "brave"

    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Query Brave Search; raise explicitly when unconfigured."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if not self._api_key:
            raise InfrastructureError("BraveProvider is not configured (missing API key)")
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
            response = await client.get(
                _BRAVE_ENDPOINT,
                headers={"X-Subscription-Token": self._api_key},
                params={"q": query, "count": limit},
            )
            response.raise_for_status()
            payload = response.json()
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(f"Brave search failed: {exc}") from exc
        results: list[SearchResult] = []
        items: object = []
        if isinstance(payload, dict):
            web = payload.get("web", {})
            items = web.get("results", []) if isinstance(web, dict) else []
        for item in items[:limit]:  # type: ignore[union-attr]
            if isinstance(item, dict):
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item.get("url", "")),
                        snippet=str(item.get("description", "")),
                        # Brave returns no normalized score; scoring
                        # happens downstream (quality/confidence layers).
                        score=0.0,
                        provider="brave",
                    )
                )
        return results
