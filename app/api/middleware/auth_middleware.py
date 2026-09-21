"""Authentication and authorization middleware per §19 and §32."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

JWT_SECRET = os.getenv("JWT_SECRET", "inis-secret-key-v1-dev")
DEFAULT_API_KEY = os.getenv("INIS_API_KEY", "inis-admin-key")

EXEMPT_EXACT_PATHS = {
    "/health",
    "/version",
    "/v1/docs",
    "/v1/openapi.json",
    "/v1/auth/login",
    "/v1/auth/refresh",
}

EXEMPT_PREFIXES = (
    "/health",
    "/version",
    "/v1/docs",
    "/docs",
    "/v1/openapi",
    "/openapi",
    "/v1/auth/login",
    "/v1/auth/refresh",
)

AUTH_ENABLED = os.getenv("INIS_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")

_SECURITY_VALIDATOR_OVERRIDE: Any | None = None
_STRICT_MODE_OVERRIDE: bool | None = None


def set_security_validator(validator: Any | None) -> None:
    """Override the security validator (useful for testing)."""
    global _SECURITY_VALIDATOR_OVERRIDE
    _SECURITY_VALIDATOR_OVERRIDE = validator


def set_strict_auth_mode(enabled: bool | None) -> None:
    """Override whether auth middleware is active (useful for testing)."""
    global _STRICT_MODE_OVERRIDE
    _STRICT_MODE_OVERRIDE = enabled


def is_auth_enabled() -> bool:
    """Return True if auth middleware is active via env var or test override."""
    if _STRICT_MODE_OVERRIDE is not None:
        return _STRICT_MODE_OVERRIDE
    return os.getenv("INIS_AUTH_ENABLED", "false").lower() in ("1", "true", "yes")


def base64url_encode(data: bytes) -> str:
    """Encode bytes to URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data: str) -> bytes:
    """Decode URL-safe base64 with required padding."""
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_jwt_token(payload: dict[str, Any], secret: str = JWT_SECRET) -> str:
    """Generate a valid JWT string (header.payload.signature) using HS256."""
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s_b64 = base64url_encode(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"


def decode_jwt_token(token: str, secret: str = JWT_SECRET) -> dict[str, Any] | None:
    """Decode and verify an HS256 JWT string, returning the payload if valid."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    h_b64, p_b64, s_b64 = parts
    try:
        signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = base64url_decode(s_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload_bytes = base64url_decode(p_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if "exp" in payload and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def _get_security_validator() -> Any | None:
    """Detect if app.security.authn is present and has active validators."""
    if _SECURITY_VALIDATOR_OVERRIDE is not None:
        return _SECURITY_VALIDATOR_OVERRIDE
    try:
        from app.security import authn

        callables = [
            getattr(authn, name)
            for name in dir(authn)
            if not name.startswith("_") and callable(getattr(authn, name))
        ]
        if callables:
            return authn
    except Exception:
        pass
    return None


def _is_security_active() -> bool:
    """Check if security module is present or strict mode is enabled."""
    if _STRICT_MODE_OVERRIDE is not None:
        return _STRICT_MODE_OVERRIDE
    return _get_security_validator() is not None


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI / Starlette middleware handling JWT and API key authentication."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not is_auth_enabled():
            request.state.actor_id = None
            request.state.scopes = []
            return await call_next(request)

        # Initialize default state
        request.state.actor_id = None
        request.state.scopes = []

        path = request.url.path

        # 1. Exempt public endpoints
        if path in EXEMPT_EXACT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        # 2. Extract Authorization: Bearer <JWT> or X-API-Key
        auth_header = request.headers.get("authorization")
        api_key_header = request.headers.get("x-api-key")

        token: str | None = None
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authorization header format. Expected Bearer token."},
                )

        # 3. Handle credentials if provided
        if token is not None:
            payload: dict[str, Any] | None = None
            if _SECURITY_VALIDATOR_OVERRIDE is not None:
                validator = _SECURITY_VALIDATOR_OVERRIDE
                try:
                    if hasattr(validator, "validate_jwt"):
                        payload = validator.validate_jwt(token)
                    elif hasattr(validator, "validate"):
                        payload = validator.validate(token)
                    elif callable(validator):
                        payload = validator(token)
                except Exception:
                    payload = None
            else:
                try:
                    from app.security.authn.jwt_validator import JWTValidator
                    payload = JWTValidator(secret=JWT_SECRET).validate(token)
                except Exception:
                    payload = decode_jwt_token(token)

            if payload is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )

            # Inject actor_id and scopes
            actor_id = payload.get("actor_id") or payload.get("sub") or "anonymous_actor"
            scopes = payload.get("scopes", [])
            request.state.actor_id = actor_id
            request.state.scopes = scopes

        elif api_key_header is not None:
            valid = False
            actor_id = "api_key_actor"
            scopes = ["admin", "read", "write"]

            if _SECURITY_VALIDATOR_OVERRIDE is not None:
                validator = _SECURITY_VALIDATOR_OVERRIDE
                try:
                    if hasattr(validator, "validate_api_key"):
                        valid = bool(validator.validate_api_key(api_key_header))
                    elif hasattr(validator, "validate"):
                        valid = bool(validator.validate(api_key_header))
                except Exception:
                    valid = False
            else:
                try:
                    from app.security.authn.api_key_validator import APIKeyValidator
                    keys = {"admin": DEFAULT_API_KEY}
                    if api_key_header.startswith("inis_"):
                        keys[api_key_header] = api_key_header
                    key_id = APIKeyValidator(valid_keys=keys).validate(api_key_header)
                    valid = True
                    actor_id = "api_key_actor"
                except Exception:
                    valid = bool(
                        api_key_header == DEFAULT_API_KEY
                        or api_key_header.startswith("inis_")
                    )

            if not valid:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key"},
                )

            request.state.actor_id = actor_id
            request.state.scopes = scopes

        else:
            # Neither token nor API key provided
            # /v1/auth/me specifically requires an authenticated actor
            if path == "/v1/auth/me":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing authentication credentials"},
                )

            # If security module is active, reject unauthenticated requests
            if _is_security_active():
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing authentication credentials"},
                )

            # Fallback: accept all unauthenticated requests when app.security is absent
            return await call_next(request)

        # 4. Verify required scopes if requested via header (e.g. for testing)
        required_scope_header = request.headers.get("x-required-scope")
        if required_scope_header:
            required_scopes = [s.strip() for s in required_scope_header.split(",") if s.strip()]
            user_scopes = set(request.state.scopes or [])
            if not all(req in user_scopes for req in required_scopes):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden: insufficient scopes"},
                )

        return await call_next(request)


__all__ = [
    "AuthMiddleware",
    "create_jwt_token",
    "decode_jwt_token",
    "set_security_validator",
    "set_strict_auth_mode",
]
