"""Tests for ProviderRouter env-based auto-selection (no network)."""

import httpx
import pytest

from app.connectors.web.provider_router import ProviderRouter


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both provider keys so each test starts hermetic."""
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)


class TestProviderRouterFallback:
    """3 tests covering wikipedia fallback and key-based selection."""

    def test_no_keys_selects_wikipedia(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without keys the router defaults to the free Wikipedia provider."""
        _clean_env(monkeypatch)
        router = ProviderRouter()
        assert router.provider_ids == ("wikipedia",)
        assert router.resolve().provider_id == "wikipedia"

    def test_serper_key_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SERPER_API_KEY selects Serper even when Brave is also set."""
        _clean_env(monkeypatch)
        monkeypatch.setenv("SERPER_API_KEY", "dummy-serper")
        monkeypatch.setenv("BRAVE_API_KEY", "dummy-brave")
        router = ProviderRouter()
        assert router.provider_ids == ("serper",)
        assert router.resolve().provider_id == "serper"

    async def test_brave_key_second(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """BRAVE_API_KEY alone selects a working Brave provider (mocked HTTP)."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Subscription-Token"] == "dummy-brave"
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {
                                "title": "Climate data",
                                "url": "https://example.com/climate",
                                "description": "Stats",
                            }
                        ]
                    }
                },
            )

        _clean_env(monkeypatch)
        monkeypatch.setenv("BRAVE_API_KEY", "dummy-brave")
        router = ProviderRouter()
        assert router.provider_ids == ("brave",)

        provider = router.resolve()
        provider._client = httpx.AsyncClient(  # type: ignore[union-attr]
            transport=httpx.MockTransport(handler)
        )
        results = await router.search("climate", 5)
        assert len(results) == 1
        assert results[0].provider == "brave"

    async def test_wikipedia_search_end_to_end_mocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default router search works when Wikipedia HTTP is mocked."""
        _clean_env(monkeypatch)
        router = ProviderRouter()
        provider = router.resolve()
        provider._client = httpx.AsyncClient(  # type: ignore[union-attr]
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json=["q", ["Climat"], ["desc"], ["https://fr.wikipedia.org/wiki/X"]],
                )
            )
        )
        results = await router.search("climat", 5)
        assert len(results) == 1
        assert results[0].provider == "wikipedia"
