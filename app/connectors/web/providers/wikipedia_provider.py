"""Wikipedia search provider over httpx (§9.1, §10.1).

Free provider backed by the MediaWiki OpenSearch API: no API key needed,
used as automatic fallback when neither ``SERPER_API_KEY`` nor
``BRAVE_API_KEY`` is configured. See
https://www.mediawiki.org/wiki/API:Opensearch for the response format::

    ["query", ["Title", ...], ["description", ...], ["url", ...]]
"""

from __future__ import annotations

import httpx

from app.connectors.web.provider_router import SearchResult
from app.core.errors import InfrastructureError

_API_PATH = "/w/api.php"
_USER_AGENT = "INIS/0.1 (research pipeline; contact: inis-local)"
# Wikipedia is a curated, high-reliability source: fixed high score,
# refined downstream (quality/confidence).
WIKIPEDIA_SCORE = 0.9


class WikipediaProvider:
    """SearchProvider backed by Wikipedia OpenSearch (free, no API key)."""

    provider_id: str = "wikipedia"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
        language: str = "fr",
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._language = language or "fr"

    @property
    def endpoint(self) -> str:
        """Return the MediaWiki API endpoint for the configured language."""
        return f"https://{self._language}.wikipedia.org{_API_PATH}"

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search Wikipedia via OpenSearch; return scored results."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
            response = await client.get(
                self.endpoint,
                headers={"User-Agent": _USER_AGENT},
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": limit,
                    "namespace": 0,
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(f"Wikipedia search failed: {exc}") from exc
        return self._map_results(payload, limit)

    def _map_results(self, payload: object, limit: int) -> list[SearchResult]:
        """Map an OpenSearch payload to domain ``SearchResult``."""
        if not isinstance(payload, list) or len(payload) != 4:
            return []
        _, titles, descriptions, urls = payload
        if not isinstance(titles, list) or not isinstance(urls, list):
            return []
        snippets = descriptions if isinstance(descriptions, list) else []
        results: list[SearchResult] = []
        for index, (title, url) in enumerate(zip(titles[:limit], urls[:limit])):
            snippet = snippets[index] if index < len(snippets) else ""
            results.append(
                SearchResult(
                    title=str(title),
                    url=str(url),
                    snippet=str(snippet or ""),
                    score=WIKIPEDIA_SCORE,
                    provider="wikipedia",
                )
            )
        return results
