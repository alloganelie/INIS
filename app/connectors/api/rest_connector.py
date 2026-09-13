"""Generic REST connector over httpx implementing SourceConnector (§9).

The ``SourceConnector`` contract and its entity types (Query,
SourceCandidate, RawSource, …) are imported from the consolidated
``app.connectors.base`` module (Devin). This module holds no local
copy of the contract.
"""

from __future__ import annotations

import time
from typing import Protocol

import httpx

from app.connectors.base import ConnectorMetadata
from app.connectors.base import HealthStatus
from app.connectors.base import Query
from app.connectors.base import RawSource
from app.connectors.base import SourceCandidate
from app.connectors.base import SourceMetadata
from app.core.errors import InfrastructureError


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
        """Search the REST source; return consolidated candidates."""
        if not isinstance(query, Query):
            raise ValueError("query must be a base.Query dataclass")
        params: dict[str, str] = {"q": query.query_string}
        if query.filters:
            params.update({str(k): str(v) for k, v in query.filters.items()})
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
                location = str(item.get("url") or item.get("href") or "")
                source_id = str(item.get("source_id") or item.get("id") or location)
                metadata = {str(k): str(v) for k, v in item.items()}
                candidates.append(
                    SourceCandidate(source_id=source_id, location=location, metadata=metadata)
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Fetch the raw payload behind a candidate (stays ``raw``)."""
        if not isinstance(candidate, SourceCandidate):
            raise ValueError("candidate must be a base.SourceCandidate dataclass")
        target = candidate.location or f"{self._base_url}/items/{candidate.source_id}"
        headers, _ = self._prepare()
        try:
            client = await self._get_client()
            response = await client.get(target, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            raise InfrastructureError(f"REST retrieve failed: {exc}") from exc
        return RawSource(
            source_id=candidate.source_id,
            data=response.text,
            content_type=response.headers.get("content-type", "application/json"),
            metadata={
                "source_url": target,
                "status_code": str(response.status_code),
                "data_stage": "raw",
            },
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Describe a raw payload without interpreting it."""
        if not isinstance(raw, RawSource):
            raise ValueError("raw must be a base.RawSource dataclass")
        data = raw.data
        size_bytes = len(data) if isinstance(data, bytes) else len(str(data).encode("utf-8"))
        return SourceMetadata(source_id=raw.source_id, size_bytes=size_bytes)

    async def health_check(self) -> HealthStatus:
        """Probe ``GET /health``; never raises, reports unhealthy on failure."""
        started = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get(f"{self._base_url}/health")
            healthy = response.status_code < 500
        except Exception:
            healthy = False
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return HealthStatus(
            healthy=healthy,
            message="up" if healthy else "down: /health probe failed",
            latency_ms=latency_ms,
        )

    async def metadata(self) -> ConnectorMetadata:
        """Return static connector metadata (no I/O)."""
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="REST connector",
            version="1.0",
            supported_source_types=list(self.supported_source_types),
        )
