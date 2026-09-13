"""OAuth2 bearer handler for the REST connector (stub per mission).

Holds a bearer token and injects ``Authorization: Bearer`` headers.
Token acquisition/refresh against a real authorization server is out
of scope for this lot: :meth:`refresh` raises an explicit error until
the OAuth2 flow is implemented.
"""

from __future__ import annotations

from app.core.errors import InfrastructureError


class OAuth2Handler:
    """Bearer-token auth with explicit stub boundary for refresh."""

    def __init__(self, token: str | None = None, token_url: str | None = None) -> None:
        self._token = token
        self._token_url = token_url

    def set_token(self, token: str) -> None:
        """Store a bearer token obtained out of band."""
        if not token:
            raise ValueError("token must be a non-empty string")
        self._token = token

    def refresh(self) -> str:
        """Refresh the bearer token (stub: explicit failure)."""
        raise InfrastructureError(
            "OAuth2 refresh is not implemented in this lot (no token endpoint configured)"
        )

    def apply(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return ``(headers, params)`` copies with the Bearer header set."""
        if not self._token:
            raise InfrastructureError("OAuth2Handler has no bearer token to apply")
        new_headers = dict(headers or {})
        new_params = dict(params or {})
        new_headers["Authorization"] = f"Bearer {self._token}"
        return new_headers, new_params
