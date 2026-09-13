"""Tests for Trafilatura and Readability extractors per §9.1 (no network)."""

from app.connectors.web.extractors.readability_extractor import ReadabilityExtractor
from app.connectors.web.extractors.trafilatura_extractor import TrafilaturaExtractor

HTML = "<html><head><title>Test</title></head><body><p>Contenu</p></body></html>"
URL = "https://example.com/article"


class TestExtractors:
    """4 tests covering real-HTML extraction and invalid input."""

    async def test_trafilatura_extractor_with_real_html(self) -> None:
        """Trafilatura extracts title and text from a simple page."""
        result = await TrafilaturaExtractor().extract(HTML, URL)

        assert result["title"] == "Test"
        assert result["text"] == "Contenu"
        assert result["url"] == URL

    async def test_trafilatura_extractor_handles_invalid(self) -> None:
        """Empty HTML returns a dict with error instead of raising."""
        result = await TrafilaturaExtractor().extract("", URL)

        assert result["text"] == ""
        assert result["error"] is not None

    async def test_readability_extractor_with_real_html(self) -> None:
        """Readability extracts title and text from a simple page."""
        result = await ReadabilityExtractor().extract(HTML, URL)

        assert result["title"] == "Test"
        assert "Contenu" in result["text"]
        assert result["url"] == URL

    async def test_readability_extractor_handles_invalid(self) -> None:
        """Empty HTML returns a dict with error instead of raising."""
        result = await ReadabilityExtractor().extract("", URL)

        assert result["text"] == ""
        assert result["error"] is not None
