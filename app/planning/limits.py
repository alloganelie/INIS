"""Execution safeguards of §41.13 enforced by the pipeline.

Two bounds keep one request from monopolizing the process:

* ``max_plan_steps`` — a plan larger than the threshold is refused with the
  explicit ``PLANNING_LIMIT_EXCEEDED`` status rather than executed blindly;
* ``max_parallel_tool_calls`` — an :class:`asyncio.Semaphore`, wrapped by
  :class:`ConcurrencyLimiter`, so the number of in-flight tool calls never
  exceeds the configured budget.

Both thresholds are read from the environment (``MAX_PLAN_STEPS``,
``MAX_PARALLEL_TOOL_CALLS``) with the documented defaults, and are exposed by
``GET /v1/metrics`` under ``benchmarks`` so operators can see the active
values.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any
from typing import Final
from typing import TypeVar

#: §41.13 default thresholds (see ``GET /v1/metrics`` → ``benchmarks``).
DEFAULT_MAX_PLAN_STEPS: Final[int] = 50
DEFAULT_MAX_PARALLEL_TOOL_CALLS: Final[int] = 10

#: §1.3-adjacent status raised when a plan exceeds ``max_plan_steps``.
PLANNING_LIMIT_EXCEEDED_STATUS: Final[str] = "PLANNING_LIMIT_EXCEEDED"

T = TypeVar("T")


def max_plan_steps() -> int:
    """Return the active ``max_plan_steps`` safeguard threshold."""
    return _positive_env_int("MAX_PLAN_STEPS", DEFAULT_MAX_PLAN_STEPS)


def max_parallel_tool_calls() -> int:
    """Return the active ``max_parallel_tool_calls`` safeguard threshold."""
    return _positive_env_int("MAX_PARALLEL_TOOL_CALLS", DEFAULT_MAX_PARALLEL_TOOL_CALLS)


def _positive_env_int(name: str, default: int) -> int:
    """Read *name* from the environment, ignoring unusable values."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def exceeds_plan_limit(step_count: int, limit: int | None = None) -> bool:
    """Return whether *step_count* breaches the plan safeguard."""
    return step_count > (max_plan_steps() if limit is None else limit)


class ConcurrencyLimiter:
    """Bound the number of concurrent tool calls with a semaphore (§41.13).

    The limiter also tracks the observed peak so an operator (and the test
    suite) can prove the bound held; ``peak_active`` never exceeds ``limit``.
    """

    def __init__(self, limit: int | None = None) -> None:
        self._limit = max(1, int(limit if limit is not None else max_parallel_tool_calls()))
        self._semaphore = asyncio.Semaphore(self._limit)
        self._active = 0
        self._peak_active = 0
        self._acquired = 0

    @property
    def limit(self) -> int:
        """Return the configured maximum number of concurrent calls."""
        return self._limit

    @property
    def active(self) -> int:
        """Return the number of calls currently in flight."""
        return self._active

    @property
    def peak_active(self) -> int:
        """Return the highest observed concurrency (never above :attr:`limit`)."""
        return self._peak_active

    @property
    def acquired(self) -> int:
        """Return how many calls went through the gate."""
        return self._acquired

    async def run(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Await ``fn(*args, **kwargs)`` while holding one slot of the gate."""
        async with self._semaphore:
            self._active += 1
            self._acquired += 1
            self._peak_active = max(self._peak_active, self._active)
            try:
                return await fn(*args, **kwargs)
            finally:
                self._active -= 1

    def stats(self) -> dict[str, int]:
        """Return the limiter counters (feeds the §34 metrics payload)."""
        return {
            "limit": self._limit,
            "active": self._active,
            "peak_active": self._peak_active,
            "acquired": self._acquired,
        }
