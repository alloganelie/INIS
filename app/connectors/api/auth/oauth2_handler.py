"""OAuth2 bearer handler for the REST connector, with refresh support (§41.4).

Holds a bearer token and injects ``Authorization: Bearer`` headers. Token
acquisition and *refresh* against a real authorization server are performed by
an injected async ``fetch_token`` callable, which keeps this module free of
direct HTTP dependencies and testable with a plain coroutine.

The token itself is never logged: :meth:`safe_state` is the only representation
intended for logs and ``audit_event`` (§41.4).
"""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.core.errors import InfrastructureError

#: Signature of the injected token endpoint: ``(refresh_token) -> token payload``.
TokenFetcher = Callable[[str], Awaitable[dict]]


class OAuth2Handler:
    """Bearer-token auth with refresh-token support (§41.4)."""

    def __init__(
        self,
        token: str | None = None,
        token_url: str | None = None,
        refresh_token: str | None = None,
        fetch_token: TokenFetcher | None = None,
        expires_at: str | None = None,
    ) -> None:
        self._token = token
        self._token_url = token_url
        self._refresh_token = refresh_token
        self._fetch_token = fetch_token
        self._expires_at = expires_at

    def set_token(self, token: str) -> None:
        """Store a bearer token obtained out of band."""
        if not token:
            raise ValueError("token must be a non-empty string")
        self._token = token

    def set_refresh_token(self, refresh_token: str) -> None:
        """Store the refresh token used by :meth:`refresh` (§41.4)."""
        if not refresh_token:
            raise ValueError("refresh_token must be a non-empty string")
        self._refresh_token = refresh_token

    def set_token_fetcher(self, fetcher: TokenFetcher) -> None:
        """Inject the coroutine that exchanges a refresh token for an access token."""
        self._fetch_token = fetcher

    def token_expiry(self) -> str | None:
        """Return the ISO-8601 UTC expiry of the current token, if known."""
        return self._expires_at

    def is_expired(self, now: datetime | None = None, skew_seconds: int = 60) -> bool:
        """Return whether the bearer token is expired (or about to be)."""
        if not self._expires_at:
            return False
        moment = now or datetime.now(UTC)
        expiry = datetime.fromisoformat(str(self._expires_at).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return moment >= expiry - timedelta(seconds=skew_seconds)

    async def refresh(self) -> str:
        """Exchange the refresh token for a new access token (§41.4).

        Raises:
            InfrastructureError: when no refresh token or no token fetcher is
                configured, or when the authorization server rejects the call.
        """
        if not self._refresh_token:
            raise InfrastructureError("OAuth2 refresh requires a refresh token (§41.4)")
        if self._fetch_token is None:
            raise InfrastructureError(
                "OAuth2 refresh requires a token fetcher; none is configured (§41.4)"
            )
        try:
            payload = await self._fetch_token(self._refresh_token)
        except Exception as exc:  # noqa: BLE001 - surfaced as an infrastructure error
            raise InfrastructureError(f"OAuth2 token refresh failed: {exc}") from exc

        token = payload.get("access_token")
        if not token:
            raise InfrastructureError("OAuth2 token endpoint returned no access_token")
        self._token = str(token)
        if payload.get("refresh_token"):
            self._refresh_token = str(payload["refresh_token"])
        if payload.get("expires_in") is not None:
            expires = datetime.now(UTC) + timedelta(seconds=int(payload["expires_in"]))
            self._expires_at = expires.isoformat().replace("+00:00", "Z")
        return self._token

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

    def safe_state(self) -> dict[str, str | None]:
        """Return a log-safe view: no token value, only its presence and expiry."""
        from app.security.vault.credential_vault import redact

        return redact(
            {
                "token_url": self._token_url,
                "has_access_token": bool(self._token),
                "has_refresh_token": bool(self._refresh_token),
                "token_expiry": self._expires_at,
            }
        )

