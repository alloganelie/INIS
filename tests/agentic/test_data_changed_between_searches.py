"""§33.3 scenario 10 — « données modifiées entre deux recherches ».

Between two searches on the same subject the source may change. INIS must not
serve the changed data from memory: the §41.5 ``on_source_update``
invalidation drops the cached entries so the next search re-fetches, and a
targeted ``invalidate_source`` re-reads only the changed page while the search
results stay cached. The delivery then carries the *new* content — the stale
one never leaks (see ``test_stale_information.py`` for the TTL-based case).

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID

OBJECTIVE = "Quelle est la capitale de la France ?"
WIKI_URL = "https://fr.wikipedia.org/wiki/Paris"

V1_TEXT = (
    "Paris est la capitale de la France. "
    "Ce document porte le marqueur version 1 des données officielles."
)
V2_TEXT = (
    "Paris est la capitale de la France. "
    "Ce document porte le marqueur version 2 des données officielles."
)


@pytest.fixture
def source_state() -> dict[str, str]:
    """Mutable stand-in for the remote page: tests edit it between two searches."""
    return {"text": V1_TEXT, "snippet": "Paris est la capitale de la France."}


@pytest.fixture
def web_doubles(
    monkeypatch: pytest.MonkeyPatch, source_state: dict[str, str]
) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers reading their payload from ``source_state``."""
    search = AsyncMock(
        side_effect=lambda query, limit: [
            SearchResult(
                title="Paris — Wikipédia",
                url=WIKI_URL,
                snippet=source_state["snippet"],
                score=0.95,
                provider="wikipedia",
            )
        ]
    )
    extract = AsyncMock(
        side_effect=lambda url: {
            "title": "Paris",
            "text": source_state["text"],
            "language": "fr",
            "url": url,
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


async def _run(runner: PipelineRunner) -> dict[str, Any]:
    return await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})


def _delivered_texts(delivery: dict[str, Any]) -> list[str]:
    """Return the factual sentences carried by the delivery findings."""
    return [
        str(finding.get("content", {}).get("text", ""))
        for finding in delivery["findings"]
    ]


@pytest.mark.asyncio
async def test_unchanged_source_is_served_from_memory(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """Control: with no change between two searches, memory answers (§41.5)."""
    runner = PipelineRunner()

    first = await _run(runner)
    searches_after_first = web_doubles["search"].await_count
    extracts_after_first = web_doubles["extract"].await_count

    second = await _run(runner)

    assert web_doubles["search"].await_count == searches_after_first
    assert web_doubles["extract"].await_count == extracts_after_first
    assert runner.get_cache_stats()["hits"] >= 1
    assert _delivered_texts(first) == _delivered_texts(second)


@pytest.mark.asyncio
async def test_page_changed_between_searches_is_refetched_for_that_source(
    web_doubles: dict[str, AsyncMock],
    source_state: dict[str, str],
) -> None:
    """A changed page is re-read (§41.5 ``on_source_update``) and the new data delivered."""
    runner = PipelineRunner()

    first = await _run(runner)
    assert any("marqueur version 1" in text for text in _delivered_texts(first))
    extracts_after_first = web_doubles["extract"].await_count
    searches_after_first = web_doubles["search"].await_count

    # The remote page changes between the two searches.
    source_state["text"] = V2_TEXT
    dropped = runner._cache.invalidate_source(f"URL:{WIKI_URL}")
    assert dropped >= 1, "the changed source entry must leave the cache"

    second = await _run(runner)

    assert web_doubles["extract"].await_count > extracts_after_first, (
        "the changed page must be re-read, not served from memory"
    )
    assert web_doubles["search"].await_count == searches_after_first, (
        "only the changed page is invalidated; the search results stay cached"
    )
    texts = _delivered_texts(second)
    assert any("marqueur version 2" in text for text in texts), "the new data must be delivered"
    assert not any("marqueur version 1" in text for text in texts), (
        "the stale version must never leak into the delivery"
    )


@pytest.mark.asyncio
async def test_source_update_event_purges_every_cached_entry(
    web_doubles: dict[str, AsyncMock],
    source_state: dict[str, str],
) -> None:
    """The §41.5 ``on_source_update`` trigger re-runs the search itself."""
    runner = PipelineRunner()

    first = await _run(runner)
    assert any("marqueur version 1" in text for text in _delivered_texts(first))
    searches_after_first = web_doubles["search"].await_count

    source_state["text"] = V2_TEXT
    source_state["snippet"] = "Paris reste la capitale (version 2)."
    dropped = runner._cache.invalidate("on_source_update")
    assert dropped >= 1, "the source update trigger must drop cached entries"

    second = await _run(runner)

    assert web_doubles["search"].await_count > searches_after_first, (
        "after a source update the query is re-searched, never served stale"
    )
    texts = _delivered_texts(second)
    assert any("marqueur version 2" in text for text in texts)
    assert not any("marqueur version 1" in text for text in texts)
