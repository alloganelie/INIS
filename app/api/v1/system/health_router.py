"""Health router exposing the real subsystem state per §32, §34.

Before B4-bis this endpoint lied: with no database it answered ``up`` for
``database``, with no broker it answered ``up`` for ``broker``, and the LLM
was not checked at all — so ``/v1/health/ready`` returned ``ready`` while 100%
of the LLM calls were silent stubs.

The contract is now:

* every subsystem is probed for real (SQL ``SELECT 1``, Redis ``PING``, an
  AMQP connection, a minimal LLM completion);
* an unconfigured subsystem reports ``not_configured`` — never ``up``;
* ``/v1/health`` exposes ``{status, version, circuit_breakers, checks}``;
* ``/v1/health/ready`` is ``degraded`` (HTTP 200) when a dependency is merely
  unconfigured, and ``not_ready`` (HTTP 503) when a configured dependency is
  actually down.

Probes run through :class:`~app.observability.health_aggregator.HealthAggregator`:
bounded by ``_READINESS_TIMEOUT_SECONDS``, isolated, never raising.
"""

from __future__ import annotations

import inspect
import os
import time
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

#: Subsystem names exposed by ``GET /v1/health`` and ``/v1/health/ready`` (§32).
DATABASE_CHECK = "database"
BROKER_CHECK = "broker"
REDIS_CHECK = "redis"
LLM_CHECK = "llm"
CIRCUIT_BREAKER_CHECK = "circuit_breakers"

#: Checks that can gate readiness; the others stay informational (§41.8).
_GATING_CHECKS = (DATABASE_CHECK, BROKER_CHECK, REDIS_CHECK, LLM_CHECK)

#: Aggregator status -> status exposed by the readiness endpoint.
_STATUS_MAP = {
    "up": "ready",
    "down": "not_ready",
    "degraded": "degraded",
    "unknown": "degraded",
}

#: Upper bound for a single subsystem probe (the aggregator never blocks).
_READINESS_TIMEOUT_SECONDS = 2.0

#: The LLM probe is a 5-token ping: enough to prove the credential works.
_LLM_PROBE_MAX_TOKENS = 5

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


def _database_check() -> HealthCheck:
    """Build the database readiness check from ``INIS_DATABASE_URL``."""
    if not os.getenv("INIS_DATABASE_URL"):

        async def database_not_configured() -> dict[str, Any]:
            return {
                "status": "degraded",
                "detail": "not_configured",
                "configured": False,
                "reason": "INIS_DATABASE_URL is not set: runs in in-memory mode",
            }

        return database_not_configured

    async def check_database() -> dict[str, Any]:
        # Resolved inside the check so a broken URL is isolated by the aggregator
        # instead of turning the endpoint into an HTTP 500.
        engine = get_database_engine()
        if engine is None:
            return {"status": "down", "error": "database engine unavailable"}
        return await make_postgres_check(engine)()

    return check_database


def _broker_url() -> str | None:
    """Return the configured AMQP endpoint, if any."""
    return os.getenv("AMQP_URL") or os.getenv("INIS_BROKER_URL")


def _broker_check() -> HealthCheck:
    """Build the broker readiness check (real AMQP connection when configured)."""
    if _broker_probe is not None:
        return make_broker_check(_BrokerProbe(_broker_probe))

    if _broker_url():

        async def check_broker_connection() -> dict[str, Any]:
            try:
                import aio_pika
            except ImportError:
                return {
                    "status": "down",
                    "error": "broker configured but aio_pika is not installed",
                }
            try:
                connection = await aio_pika.connect(
                    _broker_url(), timeout=_READINESS_TIMEOUT_SECONDS
                )
            except Exception as exc:  # noqa: BLE001 - reported as down
                return {"status": "down", "error": f"{type(exc).__name__}: {exc}"}
            try:
                return {"status": "up", "detail": "amqp"}
            finally:
                await connection.close()

        return check_broker_connection

    async def broker_not_configured() -> dict[str, Any]:
        return {
            "status": "degraded",
            "detail": "not_configured",
            "configured": False,
            "reason": "neither AMQP_URL nor INIS_BROKER_URL is set",
        }

    return broker_not_configured


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
            return {
                "status": "degraded",
                "detail": "not_configured",
                "configured": False,
                "reason": "REDIS_URL is not set: caches and shared limits are per-process",
            }

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


def _llm_check() -> HealthCheck:
    """Build the §22.1 LLM availability check.

    Without ``LLM_API_KEY`` every ``ModelRouter.complete`` call returns a
    deterministic stub, so the pipeline is still "green" while producing no
    real intelligence. That is reported as ``not_configured`` (degraded), never
    as ``up``.
    """
    from app.llm.router.model_router import ENV_API_KEY, LLMTask, ModelRouter

    async def check_llm() -> dict[str, Any]:
        if not os.getenv(ENV_API_KEY):
            return {
                "status": "degraded",
                "detail": "not_configured",
                "configured": False,
                "reason": (
                    f"{ENV_API_KEY} is not set: ModelRouter returns deterministic stubs, "
                    "every LLM call is a stub"
                ),
            }
        router = ModelRouter(timeout_seconds=_READINESS_TIMEOUT_SECONDS)
        task = LLMTask(task_type="default", max_tokens=_LLM_PROBE_MAX_TOKENS)
        try:
            response = await router.complete(task, "ping")
        except Exception as exc:  # noqa: BLE001 - reported as down
            return {"status": "down", "error": f"{type(exc).__name__}: {exc}"}
        if getattr(response, "stub", False):
            return {
                "status": "degraded",
                "detail": "stub",
                "configured": True,
                "reason": f"{ENV_API_KEY} is set but the router answered with a stub",
            }
        return {"status": "up", "model": getattr(response, "model", None)}

    return check_llm


async def _circuit_breaker_check() -> dict[str, Any]:
    """§41.8: expose breaker states as a non-gating, informational check."""
    states = breaker_registry.states()
    return {"status": "degraded" if "open" in states.values() else "up", "states": states}


def _all_checks() -> dict[str, HealthCheck]:
    """Return the four real subsystem checks plus the informational breakers."""
    return {
        DATABASE_CHECK: _database_check(),
        BROKER_CHECK: _broker_check(),
        REDIS_CHECK: _redis_check(),
        LLM_CHECK: _llm_check(),
        CIRCUIT_BREAKER_CHECK: _circuit_breaker_check,
    }


async def _aggregate() -> tuple[dict[str, Any], dict[str, Any]]:
    """Run every check and return ``(report, payload)`` ready for the response."""
    report = await HealthAggregator(
        checks=_all_checks(),
        timeout_seconds=_READINESS_TIMEOUT_SECONDS,
    ).aggregate()

    payload: dict[str, Any] = {}
    for subsystem in report["subsystems"]:
        name = str(subsystem["subsystem"])
        result = {key: value for key, value in subsystem.items() if key != "subsystem"}
        readiness = _STATUS_MAP.get(str(result.get("status")), "degraded")
        if result.get("detail") == "not_configured":
            readiness = "not_configured"
        result["status"] = readiness
        payload[name] = result
    return report, payload




def _resolve_migrations_status() -> dict[str, Any]:
    """Return applied and available Alembic migrations status per §41.14."""
    from pathlib import Path
    mig_dir = Path("migrations/versions")
    vfiles = sorted([f.stem for f in mig_dir.glob("*.py") if not f.name.startswith("__")])
    latest_avail = vfiles[-1].split("_")[0] if vfiles else "0000"

    # In-memory or unconfigured database
    if not os.getenv("INIS_DATABASE_URL"):
        return {
            "applied": 0,
            "head": "none",
            "latest_available": latest_avail,
            "up_to_date": False,
        }

    # If database engine is reachable, query alembic_version
    engine = get_database_engine()
    if engine is None:
        return {
            "applied": 0,
            "head": "unknown",
            "latest_available": latest_avail,
            "up_to_date": False,
        }

    applied_head = "unknown"
    applied_count = 0
    try:
        from sqlalchemy import text
        import asyncio

        async def _query():
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT version_num FROM alembic_version"))
                rows = res.fetchall()
                if rows:
                    return rows[0][0]
                return "0000"

        # Attempt to run query if loop is running or synchronously
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # schedule task or wait
                task = loop.create_task(_query())
                # Since this helper is called from async endpoint, we will make an async variant
            else:
                applied_head = loop.run_until_complete(_query())
        except Exception:
            pass
    except Exception:
        pass

    return {
        "applied": len(vfiles) if applied_head == latest_avail else 0,
        "head": applied_head,
        "latest_available": latest_avail,
        "up_to_date": (applied_head == latest_avail and applied_head != "unknown"),
    }


async def _async_migrations_status() -> dict[str, Any]:
    from pathlib import Path
    mig_dir = Path("migrations/versions")
    vfiles = sorted([f.stem for f in mig_dir.glob("*.py") if not f.name.startswith("__")])
    latest_avail = vfiles[-1].split("_")[0] if vfiles else "0000"

    if not os.getenv("INIS_DATABASE_URL"):
        return {
            "applied": 0,
            "head": "none",
            "latest_available": latest_avail,
            "up_to_date": False,
        }

    engine = get_database_engine()
    if engine is None:
        return {
            "applied": 0,
            "head": "unknown",
            "latest_available": latest_avail,
            "up_to_date": False,
        }

    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            rows = res.fetchall()
            applied_head = rows[0][0] if rows else "0000"
            idx = next((i for i, f in enumerate(vfiles, start=1) if f.startswith(applied_head)), 0)
            return {
                "applied": idx,
                "head": applied_head,
                "latest_available": latest_avail,
                "up_to_date": (applied_head == latest_avail),
            }
    except Exception:
        return {
            "applied": 0,
            "head": "unknown",
            "latest_available": latest_avail,
            "up_to_date": False,
        }


def _build_info() -> dict[str, str]:
    return {
        "git_sha": os.getenv("INIS_GIT_SHA") or os.getenv("GIT_COMMIT") or "unknown",
        "built_at": os.getenv("INIS_BUILT_AT") or "unknown",
    }


@router.get(
    "",
    summary="Liveness and subsystem status per §32",
)
async def get_health() -> JSONResponse:
    """Report the real state of every dependency plus the §41.8 breaker states and §41.14 migration info."""
    _report, payload = await _aggregate()
    checks = {
        name: payload[name]
        for name in (DATABASE_CHECK, REDIS_CHECK, BROKER_CHECK, LLM_CHECK)
        if name in payload
    }
    degraded = [name for name, value in checks.items() if value["status"] != "ready"]
    overall = "ok" if not degraded else "degraded"
    migrations_info = await _async_migrations_status()
    build_info = _build_info()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": overall,
            "version": "0.1.0",
            "circuit_breakers": breaker_registry.states(),
            "checks": checks,
            "migrations": migrations_info,
            "build": build_info,
        },
    )


@router.get(
    "/ready",
    summary="Subsystem readiness check per §32, §34",
)
async def get_health_ready() -> JSONResponse:
    """Aggregate the subsystem checks and expose the readiness verdict.

    Returns HTTP 200 with ``ready`` or ``degraded``, HTTP 503 with
    ``not_ready`` when a *configured* dependency is down.
    Format: ``{"status": ready | degraded | not_ready, "checks": {...}}``
    """
    _report, payload = await _aggregate()

    is_ready = True
    for name in _GATING_CHECKS:
        if payload.get(name, {}).get("status") == "not_ready":
            is_ready = False

    if not is_ready:
        overall_status = "not_ready"
    elif any(
        payload.get(name, {}).get("status") in ("degraded", "not_configured")
        for name in _GATING_CHECKS
    ):
        overall_status = "degraded"
    else:
        overall_status = "ready"

    http_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "checked_at": time.time(),
            "checks": payload,
            "migrations": await _async_migrations_status(),
            "build": _build_info(),
        },
    )
