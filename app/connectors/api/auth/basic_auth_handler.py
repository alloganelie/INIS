"""HTTP Basic auth handler for the REST connector (pure logic, no I/O)."""

from __future__ import annotations

import base64


class BasicAuthHandler:
    """Build an ``Authorization: Basic`` header (RFC 7617).

    Pure: :meth:`apply` only builds ``(headers, params)`` dicts, the
    connector performs the actual HTTP call. Credentials are never
    logged; only the header value is produced on demand.
    """

    def __init__(self, username: str, password: str) -> None:
        if not username:
            raise ValueError("username must be a non-empty string")
        if password is None:
            raise ValueError("password must not be None")
        self._username = username
        self._password = password

    @property
    def credentials(self) -> tuple[str, str]:
        """Return ``(username, password)`` for httpx ``auth=`` usage."""
        return (self._username, self._password)

    def apply(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return ``(headers, params)`` copies with the Basic header set."""
        new_headers = dict(headers or {})
        new_params = dict(params or {})
        token = base64.b64encode(f"{self._username}:{self._password}".encode("utf-8")).decode(
            "ascii"
        )
        new_headers["Authorization"] = f"Basic {token}"
        return new_headers, new_params
