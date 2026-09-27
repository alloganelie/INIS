"""Health router providing health and readiness endpoints per §32, §34.

Readiness is delegated to
:class:`app.observability.health_aggregator.HealthAggregator`: every subsystem
check runs under a bounded timeout, exceptions are isolated as ``down``, and an
unreachable dependency never blocks the endpoint. The aggregator is the single
implementation of the readiness logic; this router only maps its report onto the
HTTP contract ``{"status": ready|not_ready, "checks": {...}}``, plus the §41.8
circuit breaker states, which are informational and never gate readiness.
"""

from __future__ import annotations

import inspect
import os
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.v1.sources.repository import get_database_engine
from app.connectors.resilience.circuit_breaker import registry as breaker_registry
from app.observability.health_aggregator import (
    HealthAggregator,
    HealthCheck,
    make_broker_check,
    make_postgres_check,
    make_redis_check,
)

router = APIRouter(prefix="/health", tags=["system"])

#: Subsystem names exposed by ``GET /v1/health/ready`` (§32 contract).
DATABASE_CHECK = "database"
BROKER_CHECK = "broker"
REDIS_CHECK = "redis"
CIRCUIT_BREAKER_CHECK = "circuit_breakers"

#: Checks that can gate readiness; the others stay informational (§41.8).
_GATING_CHECKS = (DATABASE_CHECK, BROKER_CHECK, REDIS_CHECK)

#: Aggregator status → status exposed by this endpoint.
_STATUS_MAP = {
    "up": "ready",
    "down": "not_ready",
    "degraded": "degraded",
    "unknown": "degraded",
}

#: Upper bound for a single subsystem probe (the aggregator never blocks).
_READINESS_TIMEOUT_SECONDS = 2.0

_broker_probe: Any | None = None
_redis_probe: Any | None = None
_redis_client: Any | None = None


def set_broker_check(broker: Any | None) -> None:
    """Register an active broker (or a callable probe) for the readiness check."""
    global _broker_probe
    _broker_probe = broker


def set_redis_check(client: Any | None) -> None:
    """Register an active Redis client (or a callable probe) for the readiness check."""
    global _redis_probe
    _redis_probe = client


async def _maybe_await(value: Any) -> Any:
    """Return *value* after awaiting it when it is awaitable."""
    return await value if inspect.isawaitable(value) else value


def _as_status(result: Any) -> dict[str, Any]:
    """Map a probe answer onto the aggregator status vocabulary."""
    if result is True:
        return {"status": "up"}
    if isinstance(result, dict):
        if str(result.get("status", "")).lower() in ("up", "ready"):
            return {"status": "up", **{k: v for k, v in result.items() if k != "status"}}
        return {"status": "down", "detail": result}
    return {"status": "up"}


class _BrokerProbe:
    """Adapts a registered broker (health_check, callable or flag) to the aggregator."""

    def __init__(self, broker: Any) -> None:
        self._broker = broker

    async def health_check(self) -> dict[str, Any]:
        """Return the broker readiness as an aggregator status dict."""
        health = getattr(self._broker, "health_check", None)
        if callable(health):
            return _as_status(await _maybe_await(health()))
        if callable(self._broker):
            return _as_status(await _maybe_await(self._broker()))
        if hasattr(self._broker, "is_connected"):
            if self._broker.is_connected:
                return {"status": "up"}
            return {"status": "down", "error": "broker is not connected"}
        return {"status": "up"}


async def _in_memory_database() -> dict[str, Any]:
    """Default database answer when no database is configured (§32)."""
    return {"status": "up", "detail": "in_memory"}


def _database_check() -> HealthCheck:
    """Build the database readiness check from ``INIS_DATABASE_URL``."""
    if not os.getenv("INIS_DATABASE_URL"):
        return _in_memory_database

    async def check_database() -> dict[str, Any]:
        # Resolved inside the check so a broken URL is isolated by the aggregator
        # instead of turning the endpoint into an HTTP 500.
        engine = get_database_engine()
        if engine is None:
            return {"status": "down", "error": "database engine unavailable"}
        return await make_postgres_check(engine)()

    return check_database


def _broker_check() -> HealthCheck:
    """Build the broker readiness check (``not_applicable`` when unconfigured)."""
    if _broker_probe is not None:
        return make_broker_check(_BrokerProbe(_broker_probe))

    if os.getenv("AMQP_URL") or os.getenv("INIS_BROKER_URL"):

        async def broker_missing() -> dict[str, Any]:
            return {
                "status": "down",
                "error": "broker configured but no connected instance found",
            }

        return broker_missing

    async def broker_not_applicable() -> dict[str, Any]:
        return {"status": "up", "detail": "not_applicable"}

    return broker_not_applicable


def _redis_client_from_env() -> Any | None:
    """Build (once) a Redis client from ``REDIS_URL`` when the package is installed."""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL")
        if not url:
            return None
        try:
            from redis import asyncio as redis_asyncio
        except ImportError:
            return None
        _redis_client = redis_asyncio.from_url(url)
    return _redis_client


def _redis_check() -> HealthCheck:
    """Build the Redis readiness check from a registered probe or ``REDIS_URL``."""
    if _redis_probe is None and not os.getenv("REDIS_URL"):

        async def redis_not_configured() -> dict[str, Any]:
            return {"status": "up", "detail": "not_configured"}

        return redis_not_configured

    probe = _redis_probe if _redis_probe is not None else _redis_client_from_env()
    if probe is None:

        async def redis_unavailable() -> dict[str, Any]:
            return {"status": "down", "error": "REDIS_URL configured but redis client unavailable"}

        return redis_unavailable

    if callable(getattr(probe, "ping", None)):
        return make_redis_check(probe)

    if not callable(probe):

        async def redis_invalid() -> dict[str, Any]:
            return {"status": "down", "error": "redis probe must expose ping() or be callable"}

        return redis_invalid

    async def redis_probe_callable() -> dict[str, Any]:
        return _as_status(await _maybe_await(probe()))

    return redis_probe_callable


async def _circuit_breaker_check() -> dict[str, Any]:
    """§41.8: expose breaker states as a non-gating, informational check."""
    states = breaker_registry.states()
    return {"status": "degraded" if "open" in states.values() else "up", "states": states}


@router.get(
    "",
    summary="Basic liveness check per §32",
)
def get_health() -> dict[str, Any]:
    """Basic health check returning operational status.

    Also exposes the per-scope circuit breaker states ``open | closed |
    half_open`` required by §41.8.
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "circuit_breakers": breaker_registry.states(),
    }


@router.get(
    "/ready",
    summary="Subsystem readiness check per §32, §34",
)
async def get_health_ready() -> JSONResponse:
    """Aggregate the subsystem checks and expose the readiness verdict.

    Every check runs through
    :class:`~app.observability.health_aggregator.HealthAggregator`: bounded by
    ``_READINESS_TIMEOUT_SECONDS``, isolated from the others, and reported as
    ``down`` when it raises.

    Returns HTTP 200 when every gating subsystem is up, HTTP 503 otherwise.
    Format: {"status": "ready" | "not_ready", "checks": {...}}
    """
    checks: dict[str, HealthCheck] = {
        DATABASE_CHECK: _database_check(),
        BROKER_CHECK: _broker_check(),
        REDIS_CHECK: _redis_check(),
        CIRCUIT_BREAKER_CHECK: _circuit_breaker_check,
    }
    report = await HealthAggregator(
        checks=checks,
        timeout_seconds=_READINESS_TIMEOUT_SECONDS,
    ).aggregate()

    payload: dict[str, Any] = {}
    is_ready = True
    for subsystem in report["subsystems"]:
        name = str(subsystem["subsystem"])
        readiness = _STATUS_MAP.get(str(subsystem.get("status")), "degraded")
        result = {key: value for key, value in subsystem.items() if key != "subsystem"}
        result["status"] = readiness
        payload[name] = result
        if name in _GATING_CHECKS and readiness == "not_ready":
            is_ready = False

    overall_status = "ready" if is_ready else "not_ready"
    http_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "checks": payload,
        },
    )
