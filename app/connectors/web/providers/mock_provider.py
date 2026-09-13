"""Deterministic in-memory search provider (tests only)."""

from __future__ import annotations

from app.connectors.web.provider_router import SearchResult


class MockProvider:
    """SearchProvider returning deterministic canned results (no I/O)."""

    provider_id: str = "mock"

    def __init__(self, documents: list[SearchResult] | None = None) -> None:
        self._documents: list[SearchResult] = list(
            documents
            if documents is not None
            else [
                SearchResult(
                    title="Official source on climate data",
                    url="https://example.gov/climate",
                    snippet="Official statistics about climate indicators.",
                    reliability_score=0.95,
                ),
                SearchResult(
                    title="Research article on climate models",
                    url="https://example.edu/papers/climate-models",
                    snippet="Peer-reviewed analysis of climate models.",
                    reliability_score=0.85,
                ),
                SearchResult(
                    title="Forum discussion about weather",
                    url="https://forum.example.com/weather-thread",
                    snippet="Community opinions about local weather.",
                    reliability_score=0.2,
                ),
            ]
        )

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Filter canned documents by substring (case-insensitive)."""
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        lowered = query.lower()
        matched = [
            doc
            for doc in self._documents
            if lowered in f"{doc.title} {doc.snippet}".lower()
        ]
        return matched[:limit]
