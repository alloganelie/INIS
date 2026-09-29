"""§9/§10 — the web connector: routing, search and per-provider resilience.

§10.1 routes a search to the configured provider; §41.8 makes a provider that
keeps failing stop being called until its recovery window elapses. This test
runs the real ``ProviderRouter`` and the real ``WikipediaProvider`` over an
``httpx.MockTransport`` (the shared ``mock_web`` fixture), so the HTTP call path,
the result parsing and the breaker wiring are all exercised together without
touching the network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.connectors.resilience.circuit_breaker import DEFAULT_FAILURE_THRESHOLD
from app.connectors.resilience.circuit_breaker import CircuitOpenError
from app.connectors.resilience.circuit_breaker import registry as breaker_registry
from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
from app.connectors.web.provider_router import ProviderRouter, SearchResult
from app.connectors.web.providers.wikipedia_provider import WikipediaProvider

# The async tests run under the suite-wide ``asyncio_mode = "auto"`` (§33.2).


class StubProvider:
    """Minimal ``SearchProvider`` whose behaviour each test controls."""

    provider_id = "stub"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []
        self.calls = 0

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """Count the call and return the canned results."""
        self.calls += 1
        return self._results[:limit]


class TestProviderRouting:
    """§10.1 — the router resolves a provider and delegates to it."""

    async def test_search_delegates_to_the_resolved_provider(self) -> None:
        """The default provider answers the query."""
        provider = StubProvider(
            [
                SearchResult(
                    title="Paris", url="https://ex.org/p", snippet="", score=0.5, provider="stub"
                )
            ]
        )
        router = ProviderRouter(providers={"stub": provider}, default_provider_id="stub")

        results = await router.search("capitale de la France", limit=5)

        assert provider.calls == 1
        assert [result.title for result in results] == ["Paris"]

    async def test_limit_is_applied(self) -> None:
        """The provider receives the requested limit."""
        provider = StubProvider(
            [
                SearchResult(
                    title=f"r{i}",
                    url=f"https://ex.org/{i}",
                    snippet="",
                    score=0.1,
                    provider="stub",
                )
                for i in range(5)
            ]
        )
        router = ProviderRouter(providers={"stub": provider}, default_provider_id="stub")

        results = await router.search("query", limit=2)

        assert len(results) == 2

    @pytest.mark.parametrize(("query", "limit"), [("", 1), (None, 1), ("q", 0)])
    async def test_invalid_search_arguments_are_refused(self, query: object, limit: int) -> None:
        """A malformed search never reaches a provider."""
        provider = StubProvider()
        router = ProviderRouter(providers={"stub": provider}, default_provider_id="stub")

        with pytest.raises(ValueError):
            await router.search(query, limit=limit)  # type: ignore[arg-type]

        assert provider.calls == 0

    async def test_unknown_provider_is_refused(self) -> None:
        """Resolving an unregistered provider is an error, not a silent default."""
        router = ProviderRouter(providers={"stub": StubProvider()}, default_provider_id="stub")

        with pytest.raises(ValueError, match="Unknown search provider"):
            router.resolve("brave")

    def test_provider_ids_are_sorted_and_stable(self) -> None:
        """The registered providers are listed deterministically."""
        router = ProviderRouter(
            providers={"zulu": StubProvider(), "alpha": StubProvider()},
            default_provider_id="alpha",
        )

        assert router.provider_ids == ("alpha", "zulu")

    def test_register_refuses_a_malformed_provider(self) -> None:
        """A provider must expose an id and a search method."""
        router = ProviderRouter(providers={"stub": StubProvider()})

        with pytest.raises(ValueError):
            router.register(object())  # type: ignore[arg-type]


class TestProviderResilience:
    """§41.8 — a failing provider is isolated, not retried forever."""

    async def test_breaker_opens_after_repeated_failures(self) -> None:
        """Consecutive failures (§41.8 threshold) stop the provider being called."""
        provider = StubProvider()
        provider.search = AsyncMock(side_effect=RuntimeError("provider down"))  # type: ignore[method-assign]
        router = ProviderRouter(providers={"stub": provider}, default_provider_id="stub")

        for _ in range(DEFAULT_FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                await router.search("query", limit=1)

        with pytest.raises(CircuitOpenError):
            await router.search("query", limit=1)

    async def test_reset_restores_the_provider(self) -> None:
        """Closing the breaker makes the provider callable again (half-open)."""
        provider = StubProvider()
        provider.search = AsyncMock(side_effect=RuntimeError("provider down"))  # type: ignore[method-assign]
        router = ProviderRouter(providers={"stub": provider}, default_provider_id="stub")
        scope = "provider:stub"

        for _ in range(DEFAULT_FAILURE_THRESHOLD):
            with pytest.raises(RuntimeError):
                await router.search("query", limit=1)

        breaker_registry.reset(default_config=CircuitBreakerConfig())
        provider.search = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                SearchResult(
                    title="ok", url="https://ex.org", snippet="", score=0.9, provider="stub"
                )
            ]
        )

        results = await router.search("query", limit=1)

        assert [result.title for result in results] == ["ok"]
        assert breaker_registry.get(scope).allow() is True


class TestLiveProviderOverMockTransport:
    """§9.1/§10.1 — the real provider parses a real HTTP answer."""

    async def test_wikipedia_provider_maps_the_opensearch_payload(
        self, mock_web: object
    ) -> None:
        """The provider turns the MediaWiki answer into domain results."""
        router = ProviderRouter(
            providers={"wikipedia": WikipediaProvider()}, default_provider_id="wikipedia"
        )

        results = await router.search("Paris", limit=3)

        assert results, "the mocked OpenSearch answer must yield a result"
        assert results[0].provider == "wikipedia"
        assert results[0].url.startswith("http")
        assert results[0].score > 0

    def test_default_provider_falls_back_to_wikipedia_without_api_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§10.1 — with no key configured the free provider is selected."""
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)

        router = ProviderRouter()

        assert router.provider_ids == ("wikipedia",)

