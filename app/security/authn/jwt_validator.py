"""JWT validation per INIS §19.2."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.errors import ValidationError


class JWTValidator:
    """Validate JWT tokens for API authentication."""

    def __init__(self, secret: str, algorithm: str = "HS256"):
        """Initialize JWT validator.

        Args:
            secret: Secret key for HMAC signature verification
            algorithm: Signing algorithm (default HS256)
        """
        self.secret = secret
        self.algorithm = algorithm

    def validate(self, token: str) -> dict[str, Any]:
        """Validate JWT token and return payload.

        Args:
            token: JWT token string

        Returns:
            Decoded payload if valid

        Raises:
            ValidationError: If token is invalid or expired
        """
        try:
            header, payload, signature = self._split_token(token)
            self._verify_signature(header, payload, signature)
            decoded_payload = self._decode_payload(payload)
            self._check_expiration(decoded_payload)
            return decoded_payload
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            raise ValidationError(f"Invalid JWT token: {e}")

    def _split_token(self, token: str) -> tuple[str, str, str]:
        """Split JWT token into header, payload, and signature."""
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Token must have 3 parts")
        return parts

    def _decode_base64(self, data: str) -> str:
        """Decode base64url string."""
        data += "=" * ((4 - len(data) % 4) % 4)
        return base64.urlsafe_b64decode(data).decode("utf-8")

    def _verify_signature(self, header: str, payload: str, signature: str) -> None:
        """Verify JWT signature."""
        message = f"{header}.{payload}".encode("utf-8")
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(self.secret.encode(), message, hashlib.sha256).digest()
        ).decode("utf-8").rstrip("=")

        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Invalid signature")

    def _decode_payload(self, payload: str) -> dict[str, Any]:
        """Decode and parse JWT payload."""
        decoded = self._decode_base64(payload)
        return json.loads(decoded)

    def _check_expiration(self, payload: dict[str, Any]) -> None:
        """Check if token has expired."""
        if "exp" in payload:
            exp = payload["exp"]
            if time.time() > exp:
                raise ValidationError("Token has expired")
