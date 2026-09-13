"""Web connectors (search abstraction §10, provider routing §10.1)."""

from app.connectors.web.provider_router import ProviderRouter
from app.connectors.web.provider_router import SearchProvider
from app.connectors.web.provider_router import SearchResult
from app.connectors.web.providers.brave_provider import BraveProvider
from app.connectors.web.providers.mock_provider import MockProvider
from app.connectors.web.providers.serper_provider import SerperProvider

__all__ = [
    "ProviderRouter",
    "SearchProvider",
    "SearchResult",
    "MockProvider",
    "SerperProvider",
    "BraveProvider",
]
