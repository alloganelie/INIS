"""Serper web-search provider over httpx (§9.1, §10.1).

Real implementation: POSTs the query to ``serper.dev`` and maps the
``organic`` results to domain ``SearchResult``. The API key comes from
the explicit ``api_key`` argument (tests) or, as fallback, from the
``SERPER_API_KEY`` environment variable read at call time. Without a
key the provider raises explicitly and issues no network call.
"""

from __future__ import annotations

import os

import httpx

from app.connectors.web.provider_router import SearchResult
from app.core.errors import InfrastructureError

_SERPER_ENDPOINT = "https://google.serper.dev/search"
_ENV_VAR = "SERPER_API_KEY"


def _rank_score(index: int) -> float:
    """Map a 0-based rank to a 0..1 score (1.0, 0.9, … floored at 0.1)."""
    return max(0.1, round(1.0 - 0.1 * index, 2))


class SerperProvider:
    """SearchProvider backed by Serper (stub: key required)."""

    provider_id: str = "serper"

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
        """Return the explicit key or the ``SERPER_API_KEY`` fallback."""
        return self._api_key or os.environ.get(_ENV_VAR)

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Query Serper; raise explicitly when unconfigured."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        api_key = self._resolve_key()
        if not api_key:
            raise InfrastructureError("SerperProvider is not configured (missing API key)")
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
            response = await client.post(
                _SERPER_ENDPOINT,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": limit},
            )
            response.raise_for_status()
            payload = response.json()
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(f"Serper search failed: {exc}") from exc
        results: list[SearchResult] = []
        items = payload.get("organic", []) if isinstance(payload, dict) else []
        for index, item in enumerate(items[:limit]):
            if isinstance(item, dict):
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item.get("link", "")),
                        snippet=str(item.get("snippet", "")),
                        # Serper returns no normalized score: rank-based
                        # decay, refined downstream (quality/confidence).
                        score=_rank_score(index),
                        provider="serper",
                    )
                )
        return results
