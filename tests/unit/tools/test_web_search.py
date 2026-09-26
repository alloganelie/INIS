"""Tests for the ``web_search`` internal tool (§21, §10.1)."""

import pytest

from app.core.errors import InfrastructureError
from app.domain.entities.search_result import SearchResult
from app.tools.web.web_search import web_search


class FakeProvider:
    """Minimal provider recording the query it received."""

    provider_id = "fake"

    def __init__(self, score: float = 0.5) -> None:
        self.calls: list[tuple[str, int]] = []
        self._score = score

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        self.calls.append((query, limit))
        return [
            SearchResult(
                title=f"Result {index}",
                url=f"https://example.org/{index}",
                snippet="snippet",
                score=self._score,
                provider=self.provider_id,
            )
            for index in range(limit)
        ]


class FailingProvider:
    """Provider that always fails, to check error propagation."""

    provider_id = "failing"

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        raise InfrastructureError("provider unavailable")


async def test_web_search_delegates_to_the_router() -> None:
    """The tool returns what the router returns, with the same limit."""
    from app.connectors.web.provider_router import ProviderRouter

    provider = FakeProvider()
    router = ProviderRouter(providers={"fake": provider}, default_provider_id="fake")

    results = await web_search("inis", limit=3, router=router)

    assert len(results) == 3
    assert provider.calls == [("inis", 3)]
    assert all(isinstance(result, SearchResult) for result in results)


async def test_web_search_can_target_an_explicit_provider() -> None:
    """An explicit provider id overrides the router default."""
    from app.connectors.web.provider_router import ProviderRouter

    first = FakeProvider()
    second = FakeProvider(score=0.9)
    first.provider_id = "first"
    second.provider_id = "second"
    router = ProviderRouter(
        providers={"first": first, "second": second}, default_provider_id="first"
    )

    await web_search("query", limit=1, router=router, provider_id="second")

    assert second.calls == [("query", 1)]
    assert first.calls == []


async def test_web_search_rejects_empty_query() -> None:
    """An empty query is a programming error, not an empty result set."""
    with pytest.raises(ValueError, match="query must be a non-empty string"):
        await web_search("")


async def test_web_search_rejects_non_positive_limit() -> None:
    """A non-positive limit is rejected before any provider call."""
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await web_search("query", limit=0)


async def test_web_search_propagates_provider_failures() -> None:
    """Provider failures surface instead of looking like 'no result' (§0.2)."""
    from app.connectors.web.provider_router import ProviderRouter

    router = ProviderRouter(
        providers={"failing": FailingProvider()}, default_provider_id="failing"
    )

    with pytest.raises(InfrastructureError):
        await web_search("query", limit=2, router=router)
