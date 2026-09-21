"""Tests for WikipediaExtractor per §9.1 (httpx MockTransport, no network)."""

import httpx

from app.connectors.web.extractors.wikipedia_extractor import WikipediaExtractor

HTML = """<html><head><title>Climat — Wikipédia</title></head>
<body><article><h1>Climat</h1><p>Le climat est la distribution statistique.</p></article>
</body></html>"""
URL = "https://fr.wikipedia.org/wiki/Climat"


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


class TestWikipediaExtractor:
    """2 tests covering page extraction and fetch failure fallback."""

    async def test_extract_wikipedia_page(self) -> None:
        """Title, text and fr language come back with no error."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "fr.wikipedia.org" in str(request.url)
            return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

        result = await WikipediaExtractor(client=_client(handler)).extract(URL)

        assert result["title"] == "Climat"
        assert "distribution statistique" in result["text"]
        assert result["language"] == "fr"
        assert result["url"] == URL
        assert result["error"] is None

    async def test_extract_fetch_failure_returns_error(self) -> None:
        """A failed fetch returns the contract dict with error (never raises)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not found")

        result = await WikipediaExtractor(client=_client(handler)).extract(URL)

        assert result["text"] == ""
        assert result["language"] == "fr"
        assert result["url"] == URL
        assert result["error"] is not None
