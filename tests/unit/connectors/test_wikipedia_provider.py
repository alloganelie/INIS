"""Tests for WikipediaProvider per §10.1 (httpx MockTransport, no network)."""

import httpx
import pytest

from app.connectors.web.providers.wikipedia_provider import WikipediaProvider
from app.core.errors import InfrastructureError


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


PAYLOAD = [
    "climat",
    ["Climat", "Changement climatique"],
    ["Le climat en bref", "Le changement en bref"],
    [
        "https://fr.wikipedia.org/wiki/Climat",
        "https://fr.wikipedia.org/wiki/Changement_climatique",
    ],
]


class TestWikipediaProvider:
    """3 tests covering mapping, validation and API failure."""

    async def test_search_maps_opensearch_results(self) -> None:
        """OpenSearch titles/urls/descriptions map to scored SearchResults."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "fr.wikipedia.org"
            assert request.url.params["action"] == "opensearch"
            assert request.url.params["search"] == "climat"
            assert request.url.params["format"] == "json"
            return httpx.Response(200, json=PAYLOAD)

        results = await WikipediaProvider(client=_client(handler)).search("climat", 5)

        assert len(results) == 2
        assert results[0].title == "Climat"
        assert results[0].url == "https://fr.wikipedia.org/wiki/Climat"
        assert results[0].snippet == "Le climat en bref"
        assert all(r.score == 0.9 for r in results)
        assert all(r.provider == "wikipedia" for r in results)

    async def test_search_rejects_invalid_input(self) -> None:
        """Empty query and limit < 1 raise ValueError without any call."""
        provider = WikipediaProvider(client=_client(lambda r: httpx.Response(200, json=[])))

        with pytest.raises(ValueError, match="non-empty string"):
            await provider.search("", 5)
        with pytest.raises(ValueError, match="limit must be >= 1"):
            await provider.search("climat", 0)

    async def test_search_http_error_raises(self) -> None:
        """A 500 from the API surfaces as InfrastructureError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        with pytest.raises(InfrastructureError, match="Wikipedia search failed"):
            await WikipediaProvider(client=_client(handler)).search("climat", 5)
