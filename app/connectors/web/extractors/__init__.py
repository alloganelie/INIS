"""Web page extractors (§9.1: httpx + trafilatura + readability)."""

from app.connectors.web.extractors.readability_extractor import ReadabilityExtractor
from app.connectors.web.extractors.trafilatura_extractor import TrafilaturaExtractor
from app.connectors.web.extractors.wikipedia_extractor import WikipediaExtractor

__all__ = [
    "TrafilaturaExtractor",
    "ReadabilityExtractor",
    "WikipediaExtractor",
]
