"""Auth handlers for the REST connector."""

from app.connectors.api.auth.api_key_handler import ApiKeyHandler
from app.connectors.api.auth.basic_auth_handler import BasicAuthHandler
from app.connectors.api.auth.oauth2_handler import OAuth2Handler
from app.connectors.api.auth.vault_auth_handler import (
    VaultAuthHandler,
    rest_connector_for_source,
)

__all__ = [
    "ApiKeyHandler",
    "BasicAuthHandler",
    "OAuth2Handler",
    "VaultAuthHandler",
    "rest_connector_for_source",
]
