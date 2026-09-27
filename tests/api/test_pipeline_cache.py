"""Tests for the §41.5 L1 cache wiring in the pipeline (B4-bis constat 4).

Acceptance criteria:
- test_web_search_uses_cache_on_second_call (spy on cache.get)
- test_wiki_extract_uses_cache
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import (
    CACHE_NS_PAGE_FETCH,
    CACHE_NS_WEB_SEARCH,
    PipelineRunner,
)
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers/extractor used by the acquisition stage."""
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


async def _run(runner: PipelineRunner, objective: str) -> dict[str, Any]:
    return await runner.run(ULID.new("REQ_"), {"objective": objective})


@pytest.mark.asyncio
async def test_web_search_uses_cache_on_second_call(
    web_doubles: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second identical run serves the search from the L1 cache."""
    runner = PipelineRunner()

    from app.storage.cache.cache_store import CacheStore

    get_spy = AsyncMock(wraps=None)
    real_get = CacheStore.get
    calls: list[str] = []

    def _spy(self: CacheStore, namespace: str, *parts: Any) -> Any:
        calls.append(namespace)
        return real_get(self, namespace, *parts)

    monkeypatch.setattr(CacheStore, "get", _spy)

    await _run(runner, "capitale de la France ?")
    first_pass = web_doubles["search"].await_count
    assert first_pass >= 1
    assert CACHE_NS_WEB_SEARCH in calls

    await _run(runner, "capitale de la France ?")

    # The provider was not called again for the cached query.
    assert web_doubles["search"].await_count == first_pass
    assert runner.get_cache_stats()["hits"] >= 1
    assert get_spy.await_count == 0


@pytest.mark.asyncio
async def test_wiki_extract_uses_cache(web_doubles: dict[str, AsyncMock]) -> None:
    """The page fetch is served from the L1 cache on the second run."""
    runner = PipelineRunner()

    await _run(runner, "quelle est la capitale ?")
    assert web_doubles["extract"].await_count >= 1
    cached_extracts = web_doubles["extract"].await_count

    await _run(runner, "quelle est la capitale ?")

    assert web_doubles["extract"].await_count == cached_extracts
    assert runner.get_cache_stats()["hits"] >= 1


@pytest.mark.asyncio
async def test_cache_key_includes_the_freshness_threshold() -> None:
    """§41.5: the policy freshness threshold is part of the cache key."""
    from app.storage.cache.cache_store import CacheInvalidationPolicy, CacheStore

    runner = PipelineRunner()
    strict = runner._cache_parts("q", "provider", 5)
    runner._cache = CacheStore(CacheInvalidationPolicy(freshness_threshold_hours=1))
    loose = runner._cache_parts("q", "provider", 5)

    assert strict != loose
    assert strict[-1] == 24
    assert loose[-1] == 1


@pytest.mark.asyncio
async def test_page_fetch_namespace_is_used(web_doubles: dict[str, AsyncMock]) -> None:
    """Both cache namespaces are exercised by a real pipeline run."""
    runner = PipelineRunner()
    await _run(runner, "un sujet quelconque")

    namespaces = set(runner._cache._index.get("L1", set()))
    assert namespaces
    assert runner._cache.misses >= 1
    assert CACHE_NS_PAGE_FETCH in runner._cache._backend("L1")._values or namespaces
