"""API key validation per INIS §19.2."""

import hmac
from typing import Dict

from app.core.errors import ValidationError


class APIKeyValidator:
    """Validate API keys for administration authentication."""

    def __init__(self, valid_keys: Dict[str, str]):
        """Initialize API key validator.

        Args:
            valid_keys: Dictionary mapping key identifiers to their values
        """
        self.valid_keys = valid_keys

    def validate(self, api_key: str) -> str:
        """Validate API key using timing-safe comparison.

        Args:
            api_key: API key string to validate

        Returns:
            Key identifier if valid

        Raises:
            ValidationError: If key is invalid
        """
        for key_id, key_value in self.valid_keys.items():
            if self._timing_safe_compare(api_key, key_value):
                return key_id

        raise ValidationError("Invalid API key")

    def _timing_safe_compare(self, a: str, b: str) -> bool:
        """Timing-safe string comparison to prevent timing attacks."""
        return hmac.compare_digest(a.encode(), b.encode())
