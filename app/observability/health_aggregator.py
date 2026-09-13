"""Health aggregation over subsystem checks (never raises, never blocks).

Per ARCHITECTURE.md ``app/observability/`` must never be blocking nor
fatally in error: :meth:`HealthAggregator.aggregate` isolates every
subsystem check (timeout + exception guard) and always returns a dict.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

HealthCheck = Callable[[], Any]

_GLOBAL_STATUS_RANK = {"up": 0, "unknown": 1, "degraded": 1, "down": 2}


class HealthAggregator:
    """Aggregate injected subsystem checks into a global status.

    Global status rule: ``down`` if any subsystem is down, else
    ``degraded`` if any is unknown/degraded, else ``up``.
    """

    def __init__(
        self,
        checks: dict[str, HealthCheck] | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._checks: dict[str, HealthCheck] = dict(checks or {})
        self._timeout_seconds = timeout_seconds

    def register(self, name: str, check: HealthCheck) -> None:
        """Register (or replace) a subsystem check."""
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        if not callable(check):
            raise ValueError("check must be callable")
        self._checks[name] = check

    async def _run_one(self, name: str, check: HealthCheck) -> dict[str, Any]:
        try:
            result = check()
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=self._timeout_seconds)
            if isinstance(result, dict) and result.get("status") in _GLOBAL_STATUS_RANK:
                return {"name": name, **result}
            return {"name": name, "status": "unknown", "detail": result}
        except Exception as exc:
            return {"name": name, "status": "down", "error": f"{type(exc).__name__}: {exc}"}

    async def aggregate(self) -> dict[str, Any]:
        """Run all checks and return global status + subsystems."""
        subsystems = [await self._run_one(name, check) for name, check in self._checks.items()]
        rank = 0
        for subsystem in subsystems:
            rank = max(rank, _GLOBAL_STATUS_RANK.get(str(subsystem.get("status")), 1))
        global_status = next(name for name, value in _GLOBAL_STATUS_RANK.items() if value == rank)
        return {"status": global_status, "subsystems": subsystems}


async def aggregate(
    checks: dict[str, HealthCheck] | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """One-shot aggregation without instantiating the class."""
    return await HealthAggregator(checks, timeout_seconds).aggregate()
