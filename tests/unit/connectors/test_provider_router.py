"""Tests for ProviderRouter per §10.1 (no network)."""

import pytest

from app.connectors.web.provider_router import ProviderRouter
from app.connectors.web.providers.brave_provider import BraveProvider
from app.connectors.web.providers.mock_provider import MockProvider
from app.connectors.web.providers.serper_provider import SerperProvider
from app.core.errors import InfrastructureError


class TestProviderRouter:
    """3 tests covering routing, unknown provider and unconfigured stubs."""

    async def test_routes_to_default_mock_provider(self) -> None:
        """search delegates to the default provider and filters by query."""
        router = ProviderRouter(providers={"mock": MockProvider()})

        results = await router.search("climate", 10)

        assert len(results) == 2
        assert all("climate" in f"{r.title} {r.snippet}".lower() for r in results)

    async def test_unknown_provider_raises(self) -> None:
        """An explicit ValueError names the unknown provider."""
        router = ProviderRouter(providers={"mock": MockProvider()})

        with pytest.raises(ValueError, match="Unknown search provider: nosuch"):
            await router.search("climate", 5, provider_id="nosuch")

    async def test_unconfigured_stubs_fail_explicitly(self) -> None:
        """Serper/Brave without API key fail without any network call."""
        router = ProviderRouter(
            providers={"serper": SerperProvider(), "brave": BraveProvider()},
            default_provider_id="serper",
        )

        with pytest.raises(InfrastructureError, match="SerperProvider is not configured"):
            await router.search("climate", 5)
        with pytest.raises(InfrastructureError, match="BraveProvider is not configured"):
            await router.search("climate", 5, provider_id="brave")
