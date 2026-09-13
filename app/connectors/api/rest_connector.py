"""Generic REST connector over httpx implementing SourceConnector (§9).

NOTE — temporary local definition: ``app/connectors/base.py`` (owned
by Devin) is still an empty placeholder, so the ``SourceConnector``
protocol is redeclared locally per the §9 contract. The canonical
source of truth remains ``base.py``; this module must converge to it
as soon as Devin implements it. Entity types (Query, SourceCandidate,
RawSource, …) are likewise represented as plain dicts until
``app/domain/entities/`` provides them (Codex).
"""

from __future__ import annotations

import time
from typing import Any
from typing import Protocol
from typing import runtime_checkable

import httpx

from app.core.errors import InfrastructureError

Query = str | dict[str, Any]
SourceCandidate = dict[str, Any]
RawSource = dict[str, Any]
SourceMetadata = dict[str, Any]
HealthStatus = dict[str, Any]
ConnectorMetadata = dict[str, Any]


@runtime_checkable
class SourceConnector(Protocol):
    """Local copy of the §9 SourceConnector contract (see module note)."""

    connector_id: str
    supported_source_types: list[str]

    async def discover(self, query: Query) -> list[SourceCandidate]: ...
    async def retrieve(self, candidate: SourceCandidate) -> RawSource: ...
    async def inspect(self, raw: RawSource) -> SourceMetadata: ...
    async def health_check(self) -> HealthStatus: ...
    async def metadata(self) -> ConnectorMetadata: ...


class _AuthHandler(Protocol):
    def apply(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]: ...


class RESTConnector:
    """REST source connector (§9.1: API REST over httpx).

    The connector collects raw data only (§0.2 invariant 3: everything
    stays ``raw`` here; normalization happens downstream). Each raw
    payload keeps its origin URL so provenance can be asserted later.
    """

    connector_id: str = "rest-connector"
    supported_source_types: list[str] = ["api"]

    def __init__(
        self,
        base_url: str,
        auth_handler: _AuthHandler | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be a non-empty string")
        self._base_url = base_url.rstrip("/")
        self._auth_handler = auth_handler
        self._client = client
        self._timeout_seconds = timeout_seconds

    def _prepare(
        self,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], dict[str, str]]:
        if self._auth_handler is None:
            return dict(headers or {}), dict(params or {})
        return self._auth_handler.apply(headers, params)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        return self._client

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Search the REST source; return raw candidate dicts."""
        params: dict[str, str] = {}
        if isinstance(query, str):
            params["q"] = query
        elif isinstance(query, dict):
            params = {str(k): str(v) for k, v in query.items()}
        else:
            raise ValueError("query must be a string or a dict")
        headers, params = self._prepare(params=params)
        try:
            client = await self._get_client()
            response = await client.get(f"{self._base_url}/search", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise InfrastructureError(f"REST discover failed: {exc}") from exc
        items = payload if isinstance(payload, list) else payload.get("items", [])
        candidates: list[SourceCandidate] = []
        for item in items:
            if isinstance(item, dict):
                candidates.append(dict(item))
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Fetch the raw payload behind a candidate (stays ``raw``)."""
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be a dict")
        url = str(candidate.get("url") or candidate.get("href") or "")
        target = url or f"{self._base_url}/items/{candidate.get('id', '')}"
        headers, _ = self._prepare()
        try:
            client = await self._get_client()
            response = await client.get(target, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            raise InfrastructureError(f"REST retrieve failed: {exc}") from exc
        return {
            "data_stage": "raw",
            "source_url": target,
            "status_code": response.status_code,
            "media_type": response.headers.get("content-type", "application/json"),
            "content": response.text,
        }

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Describe a raw payload without interpreting it."""
        if not isinstance(raw, dict):
            raise ValueError("raw must be a dict")
        content = str(raw.get("content", ""))
        return {
            "media_type": raw.get("media_type", "application/json"),
            "size_bytes": len(content.encode("utf-8")),
            "source_url": raw.get("source_url"),
            "data_stage": "raw",
        }

    async def health_check(self) -> HealthStatus:
        """Probe ``GET /health``; never raises, reports down on failure."""
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(f"{self._base_url}/health")
            up = response.status_code < 500
        except Exception:
            up = False
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return {
            "status": "up" if up else "down",
            "latency_ms": latency_ms,
            "connector_id": self.connector_id,
        }

    async def metadata(self) -> ConnectorMetadata:
        """Return static connector metadata (no I/O)."""
        return {
            "connector_id": self.connector_id,
            "supported_source_types": list(self.supported_source_types),
            "base_url": self._base_url,
        }
