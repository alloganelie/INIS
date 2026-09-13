"""Web page extractors (§9.1: httpx + trafilatura + readability)."""

from app.connectors.web.extractors.readability_extractor import ReadabilityExtractor
from app.connectors.web.extractors.trafilatura_extractor import TrafilaturaExtractor

__all__ = [
    "TrafilaturaExtractor",
    "ReadabilityExtractor",
]
