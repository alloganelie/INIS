"""Web-search providers (§9.1: httpx + provider adapters)."""

from app.connectors.web.providers.brave_provider import BraveProvider
from app.connectors.web.providers.mock_provider import MockProvider
from app.connectors.web.providers.serper_provider import SerperProvider

__all__ = [
    "MockProvider",
    "SerperProvider",
    "BraveProvider",
]
