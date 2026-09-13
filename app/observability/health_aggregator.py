"""Health aggregation over subsystem checks (never raises, never blocks).

Per ARCHITECTURE.md ``app/observability/`` must never be blocking nor
fatally in error: :meth:`HealthAggregator.aggregate` isolates every
subsystem check (timeout + exception guard) and always returns a dict.

Default checks (postgres / redis / broker) are built by the
``make_*_check`` factories from duck-typed dependencies: only
Protocols are used here, never direct imports of sqlalchemy, redis or
aio-pika. Each default check is async, guarded by the aggregator
timeout, and reports ``down`` on exception.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from typing import Any
from typing import Protocol

HealthCheck = Callable[[], Any]

_GLOBAL_STATUS_RANK = {"up": 0, "unknown": 1, "degraded": 1, "down": 2}

POSTGRES_CHECK = "postgres"
REDIS_CHECK = "redis"
BROKER_CHECK = "broker"


class SqlEngine(Protocol):
    """Minimal SQL engine surface (SQLAlchemy AsyncEngine compatible)."""

    def connect(self) -> Any: ...


class RedisClient(Protocol):
    """Minimal Redis surface (redis.asyncio compatible)."""

    def ping(self) -> Any: ...


class BrokerLike(Protocol):
    """Minimal broker surface (AMQP/MQTT health compatible)."""

    def health_check(self) -> Any: ...


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def make_postgres_check(engine: SqlEngine) -> HealthCheck:
    """Build a ``SELECT 1`` + latency check from an async SQL engine."""

    async def check_postgres() -> dict[str, Any]:
        started = time.perf_counter()
        connection = engine.connect()
        if hasattr(connection, "__aenter__"):
            async with connection as conn:
                await _run_select_one(conn)
        else:
            conn = await _maybe_await(connection)
            try:
                await _run_select_one(conn)
            finally:
                close = getattr(conn, "close", None)
                if callable(close):
                    await _maybe_await(close())
        return {"status": "up", "latency_ms": round((time.perf_counter() - started) * 1000.0, 3)}

    return check_postgres


async def _run_select_one(conn: Any) -> None:
    # SQLAlchemy AsyncConnection exposes exec_driver_sql for raw strings;
    # test doubles (and other drivers) expose plain execute().
    execute = getattr(conn, "exec_driver_sql", None) or getattr(conn, "execute", None)
    if not callable(execute):
        raise TypeError("connection exposes neither exec_driver_sql nor execute")
    await _maybe_await(execute("SELECT 1"))


def make_redis_check(client: RedisClient) -> HealthCheck:
    """Build a ``PING`` + latency check from an async Redis client."""

    async def check_redis() -> dict[str, Any]:
        started = time.perf_counter()
        await _maybe_await(client.ping())
        return {"status": "up", "latency_ms": round((time.perf_counter() - started) * 1000.0, 3)}

    return check_redis


def make_broker_check(broker: BrokerLike) -> HealthCheck:
    """Build a check delegating to the broker's own ``health_check``."""

    async def check_broker() -> dict[str, Any]:
        started = time.perf_counter()
        result = await _maybe_await(broker.health_check())
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if isinstance(result, dict) and result.get("status") in _GLOBAL_STATUS_RANK:
            payload = dict(result)
            payload.setdefault("latency_ms", latency_ms)
            return payload
        return {"status": "up" if result else "down", "latency_ms": latency_ms}

    return check_broker


class HealthAggregator:
    """Aggregate injected subsystem checks into a global status.

    Global status rule: ``down`` if any subsystem is down, else
    ``degraded`` if any is unknown/degraded, else ``up``.

    When ``checks`` is None, the postgres/redis/broker default checks
    are wired for every dependency provided (``engine``,
    ``redis_client``, ``broker``); missing dependencies are skipped.
    ``checks`` also accepts a list of ``(name, check)`` tuples.
    """

    def __init__(
        self,
        checks: dict[str, HealthCheck] | list[tuple[str, HealthCheck]] | None = None,
        timeout_seconds: float = 2.0,
        engine: SqlEngine | None = None,
        redis_client: RedisClient | None = None,
        broker: BrokerLike | None = None,
    ) -> None:
        if checks is None:
            checks = self._default_checks(engine, redis_client, broker)
        elif isinstance(checks, list):
            checks = dict(checks)
        self._checks: dict[str, HealthCheck] = dict(checks)
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _default_checks(
        engine: SqlEngine | None,
        redis_client: RedisClient | None,
        broker: BrokerLike | None,
    ) -> dict[str, HealthCheck]:
        defaults: dict[str, HealthCheck] = {}
        if engine is not None:
            defaults[POSTGRES_CHECK] = make_postgres_check(engine)
        if redis_client is not None:
            defaults[REDIS_CHECK] = make_redis_check(redis_client)
        if broker is not None:
            defaults[BROKER_CHECK] = make_broker_check(broker)
        return defaults

    def register(self, name: str, check: HealthCheck) -> None:
        """Register (or replace) a subsystem check."""
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        if not callable(check):
            raise ValueError("check must be callable")
        self._checks[name] = check

    async def _run_one(self, name: str, check: HealthCheck) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = check()
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=self._timeout_seconds)
            latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
            if isinstance(result, dict) and result.get("status") in _GLOBAL_STATUS_RANK:
                payload = {"subsystem": name, **result}
                payload.setdefault("latency_ms", latency_ms)
                return payload
            return {
                "subsystem": name,
                "status": "unknown",
                "latency_ms": latency_ms,
                "detail": result,
            }
        except Exception as exc:
            return {
                "subsystem": name,
                "status": "down",
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }

    async def aggregate(self) -> dict[str, Any]:
        """Run all checks and return global status + subsystems."""
        subsystems = [await self._run_one(name, check) for name, check in self._checks.items()]
        rank = 0
        for subsystem in subsystems:
            rank = max(rank, _GLOBAL_STATUS_RANK.get(str(subsystem.get("status")), 1))
        global_status = next(name for name, value in _GLOBAL_STATUS_RANK.items() if value == rank)
        return {"status": global_status, "subsystems": subsystems}


async def aggregate(
    checks: dict[str, HealthCheck] | list[tuple[str, HealthCheck]] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """One-shot aggregation without instantiating the class.

    Accepts the same input formats as :class:`HealthAggregator`: a
    ``{name: check}`` dict or a list of ``(name, check)`` tuples.
    """
    return await HealthAggregator(checks, timeout_seconds).aggregate()
