"""§33.3 scenario 9 — « réutilisation de mémoire ».

A question already answered from a still-fresh source must be served from the
§41.5 L1 memory instead of being re-searched: the provider is called once, the
second run is a cache hit, and the hit rate is visible in the cache stats.
A *stale* entry is never reused (that case is covered by
``test_stale_information.py``).

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import CACHE_NS_WEB_SEARCH, PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.storage.cache.cache_store import CacheStore

OBJECTIVE = "Quelle est la capitale de la France ?"


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers and extractor used by the acquisition stage."""
    result = SearchResult(
        title="Paris — Wikipédia",
        url="https://fr.wikipedia.org/wiki/Paris",
        snippet="Paris est la capitale de la France.",
        score=0.95,
        provider="wikipedia",
    )
    search = AsyncMock(return_value=[result])
    extract = AsyncMock(
        return_value={
            "title": "Paris",
            "text": "Paris est la capitale de la France.",
            "language": "fr",
            "url": "https://fr.wikipedia.org/wiki/Paris",
            "error": None,
        }
    )
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


def _install_cache_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every cache namespace consulted (spy on ``CacheStore.get``)."""
    namespaces: list[str] = []
    real_get = CacheStore.get

    def _spy(self: CacheStore, namespace: str, *parts: Any) -> Any:
        namespaces.append(namespace)
        return real_get(self, namespace, *parts)

    monkeypatch.setattr(CacheStore, "get", _spy)
    return namespaces


@pytest.mark.asyncio
async def test_memory_is_reused_for_a_repeated_question(
    web_doubles: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second identical run: fresh memory is reused, the source is not re-fetched."""
    consulted = _install_cache_spy(monkeypatch)
    runner = PipelineRunner()

    first = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})
    calls_after_first = web_doubles["search"].await_count
    assert calls_after_first >= 1
    assert CACHE_NS_WEB_SEARCH in consulted

    second = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})

    assert web_doubles["search"].await_count == calls_after_first, (
        "the fresh memory must answer without a second provider call"
    )
    stats = runner.get_cache_stats()
    assert stats["hits"] >= 1
    assert stats["hit_rate"] > 0.0
    assert first["sources"] and second["sources"]


@pytest.mark.asyncio
async def test_memory_carries_the_same_findings(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """The reused memory yields the same §0.2-compliant findings."""
    runner = PipelineRunner()

    first = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})
    second = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})

    first_contents = [f.get("content", {}) for f in first["findings"]]
    second_contents = [f.get("content", {}) for f in second["findings"]]
    assert first_contents == second_contents
    assert len(second["findings"]) >= 1
    assert all(f["source_id"].startswith("SRC_") for f in second["findings"])

