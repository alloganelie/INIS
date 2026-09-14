"""Tests for JWT validation per INIS §19.2."""

import base64
import hashlib
import hmac
import json
import time

import pytest

from app.core.errors import ValidationError
from app.security.authn import JWTValidator


def create_jwt(payload: dict, secret: str) -> str:
    """Create a simple JWT for testing."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    message = f"{header_b64}.{payload_b64}".encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), message, hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature}"


def test_jwt_validator_valid_token():
    """Test validation of a valid JWT token."""
    secret = "test_secret"
    payload = {"sub": "user123", "exp": int(time.time()) + 3600}
    token = create_jwt(payload, secret)

    validator = JWTValidator(secret)
    result = validator.validate(token)

    assert result["sub"] == "user123"
    assert result["exp"] == payload["exp"]


def test_jwt_validator_invalid_signature():
    """Test validation fails with invalid signature."""
    secret = "test_secret"
    payload = {"sub": "user123", "exp": int(time.time()) + 3600}
    token = create_jwt(payload, secret)

    wrong_secret = "wrong_secret"
    validator = JWTValidator(wrong_secret)

    with pytest.raises(ValidationError, match="Invalid signature"):
        validator.validate(token)


def test_jwt_validator_expired_token():
    """Test validation fails with expired token."""
    secret = "test_secret"
    payload = {"sub": "user123", "exp": int(time.time()) - 3600}
    token = create_jwt(payload, secret)

    validator = JWTValidator(secret)

    with pytest.raises(ValidationError, match="Token has expired"):
        validator.validate(token)


def test_jwt_validator_malformed_token():
    """Test validation fails with malformed token."""
    secret = "test_secret"
    validator = JWTValidator(secret)

    with pytest.raises(ValidationError, match="Invalid JWT token"):
        validator.validate("invalid.token")


def test_jwt_validator_missing_parts():
    """Test validation fails with token missing parts."""
    secret = "test_secret"
    validator = JWTValidator(secret)

    with pytest.raises(ValidationError, match="Invalid JWT token"):
        validator.validate("only.two.parts")
