"""Serper web-search provider (§9.1, stub).

Without an API key the provider fails explicitly instead of issuing
any network call. With a key it performs a real ``serper.dev`` query
(not exercised in unit tests, which use MockProvider).
"""

from __future__ import annotations

import httpx

from app.connectors.web.provider_router import SearchResult
from app.core.errors import InfrastructureError

_SERPER_ENDPOINT = "https://google.serper.dev/search"


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

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Query Serper; raise explicitly when unconfigured."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if not self._api_key:
            raise InfrastructureError("SerperProvider is not configured (missing API key)")
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
            response = await client.post(
                _SERPER_ENDPOINT,
                headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
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
        for item in items[:limit]:
            if isinstance(item, dict):
                results.append(
                    SearchResult(
                        title=str(item.get("title", "")),
                        url=str(item.get("link", "")),
                        snippet=str(item.get("snippet", "")),
                    )
                )
        return results
