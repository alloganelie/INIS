"""Brave web-search provider over httpx (§9.1, §10.1).

Real implementation: GETs the Brave Search API and maps ``web.results``
to domain ``SearchResult``. The API key comes from the explicit
``api_key`` argument (tests) or, as fallback, from the
``BRAVE_API_KEY`` environment variable read at call time. Without a
key the provider raises explicitly and issues no network call.
"""

from __future__ import annotations

import os

import httpx

from app.connectors.web.provider_router import SearchResult
from app.core.errors import InfrastructureError

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_ENV_VAR = "BRAVE_API_KEY"


def _rank_score(index: int) -> float:
    """Map a 0-based rank to a 0..1 score (1.0, 0.9, … floored at 0.1)."""
    return max(0.1, round(1.0 - 0.1 * index, 2))


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

    def _resolve_key(self) -> str | None:
        """Return the explicit key or the ``BRAVE_API_KEY`` fallback."""
        return self._api_key or os.environ.get(_ENV_VAR)

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Query Brave Search; raise explicitly when unconfigured."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        api_key = self._resolve_key()
        if not api_key:
            raise InfrastructureError("BraveProvider is not configured (missing API key)")
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
            response = await client.get(
                _BRAVE_ENDPOINT,
                headers={"X-Subscription-Token": api_key},
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
        for index, item in enumerate(items[:limit]):  # type: ignore[union-attr]
            if isinstance(item, dict):
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item.get("url", "")),
                        snippet=str(item.get("description", "")),
                        # Brave returns no normalized score: rank-based
                        # decay, refined downstream (quality/confidence).
                        score=_rank_score(index),
                        provider="brave",
                    )
                )
        return results
