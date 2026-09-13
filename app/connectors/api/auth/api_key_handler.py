"""API-key auth handler for the REST connector (pure logic, no I/O)."""

from __future__ import annotations


class ApiKeyHandler:
    """Inject an API key as header (default) or query param.

    Pure: :meth:`apply` only builds ``(headers, params)`` dicts, the
    connector performs the actual HTTP call.
    """

    def __init__(
        self,
        api_key: str,
        header_name: str = "X-API-Key",
        in_query: bool = False,
        query_param: str = "api_key",
    ) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        self._api_key = api_key
        self._header_name = header_name
        self._in_query = in_query
        self._query_param = query_param

    def apply(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return ``(headers, params)`` copies enriched with the API key."""
        new_headers = dict(headers or {})
        new_params = dict(params or {})
        if self._in_query:
            new_params[self._query_param] = self._api_key
        else:
            new_headers[self._header_name] = self._api_key
        return new_headers, new_params
