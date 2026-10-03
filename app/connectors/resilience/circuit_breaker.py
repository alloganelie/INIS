"""Circuit breaker per connector / provider / external agent (§41.8).

Implements the ``circuit_breaker`` ``[CONFIG]`` structure of the spec:

    failure_threshold        consecutive failures that open the breaker
    recovery_timeout_seconds wait before probing again
    half_open_max_calls      probes allowed while half-open

The state machine is pure logic over an **injectable clock**, so every
transition is unit-testable without sleeping. The module-level
:data:`registry` keys breakers by scope (``provider:*``, ``connector:*``,
``agent:*``) and is the source of truth for the ``/v1/health`` exposure
required by §41.8.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app.domain.enums.circuit_breaker_state import CircuitBreakerState

T = TypeVar("T")

#: Default ``[CONFIG]`` values of §41.8.
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RECOVERY_TIMEOUT_SECONDS = 30
DEFAULT_HALF_OPEN_MAX_CALLS = 2


class CircuitOpenError(RuntimeError):
    """Raised when a call is refused because the breaker is open."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"circuit breaker open for {scope!r} (§41.8)")
        self.scope = scope


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """The three ``circuit_breaker`` ``[CONFIG]`` thresholds."""

    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    recovery_timeout_seconds: int = DEFAULT_RECOVERY_TIMEOUT_SECONDS
    half_open_max_calls: int = DEFAULT_HALF_OPEN_MAX_CALLS

    def __post_init__(self) -> None:
        for name in (
            "failure_threshold",
            "recovery_timeout_seconds",
            "half_open_max_calls",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    def to_dict(self) -> dict[str, int]:
        """Return the §41.8 ``circuit_breaker`` ``[CONFIG]`` block."""
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "half_open_max_calls": self.half_open_max_calls,
        }


DEFAULT_CIRCUIT_BREAKER_CONFIG = CircuitBreakerConfig()

class CircuitBreaker:
    """State machine ``closed -> open -> half_open -> closed`` (§41.8).

    Args:
        scope: identifies what is protected (``provider:serper``,
            ``connector:csv``, ``agent:AGT_...``).
        config: thresholds; defaults to :data:`DEFAULT_CIRCUIT_BREAKER_CONFIG`.
        clock: injectable monotonic clock (seconds); defaults to
            ``time.monotonic``.
    """

    def __init__(
        self,
        scope: str,
        config: CircuitBreakerConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.scope = scope
        self.config = config or DEFAULT_CIRCUIT_BREAKER_CONFIG
        self._clock = clock
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0

    @property
    def failure_count(self) -> int:
        """Consecutive failures recorded in the current closed window."""
        return self._failure_count

    @property
    def state(self) -> CircuitBreakerState:
        """Current state, applying the ``open -> half_open`` time transition."""
        if self._state is CircuitBreakerState.OPEN and self._opened_at is not None:
            if self._clock() - self._opened_at >= self.config.recovery_timeout_seconds:
                self._state = CircuitBreakerState.HALF_OPEN
                self._half_open_in_flight = 0
        return self._state

    def allow(self) -> bool:
        """Return whether a call may proceed, reserving a half-open slot.

        Returns:
            ``True`` when closed, or when half-open with a free probe slot;
            ``False`` when open, or when all half-open probes are in flight.
        """
        state = self.state
        if state is CircuitBreakerState.CLOSED:
            return True
        if state is CircuitBreakerState.OPEN:
            return False
        if self._half_open_in_flight < self.config.half_open_max_calls:
            self._half_open_in_flight += 1
            return True
        return False

    def record_success(self) -> None:
        """Record a successful call (half-open success closes the breaker).

        A stale success arriving while the breaker is already open (a call
        started before the breaker opened) is ignored — it must not cancel
        the recovery timer.
        """
        state = self.state
        if state is CircuitBreakerState.OPEN:
            return
        if state is CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.CLOSED
            self._half_open_in_flight = 0
        self._failure_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call, opening the breaker at the threshold.

        A failed half-open probe reopens the breaker immediately, restarting
        the recovery timeout.
        """
        state = self.state
        self._failure_count += 1
        if state is CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            self._opened_at = self._clock()
            self._half_open_in_flight = 0
        elif state is CircuitBreakerState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = self._clock()

    async def run(self, call: Callable[[], Awaitable[T]]) -> T:
        """Execute *call* under this breaker.

        Raises:
            CircuitOpenError: when the breaker refuses the call.
            Exception: whatever *call* raised (recorded as a failure).
        """
        if not self.allow():
            raise CircuitOpenError(self.scope)
        try:
            result = await call()
        except CircuitOpenError:
            raise
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection exposed in ``/v1/health``."""
        return {
            "scope": self.scope,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "config": self.config.to_dict(),
        }


async def guard(
    scope: str,
    call: Callable[[], Awaitable[T]],
    *,
    breaker_registry: CircuitBreakerRegistry | None = None,
    max_attempts: int = 1,
    base_delay_seconds: float = 0.0,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> T:
    """Run *call* behind the §41.8 breaker of *scope*, retrying transient failures.

    The two mechanisms answer two different questions and are therefore composed
    here, in this order:

    * **retry** — "this call failed, is another attempt likely to work?" Only a
      call that can be repeated safely may be retried, which is why
      ``max_attempts`` defaults to **1**: a caller that does not know its call is
      repeatable gets one attempt, never a silent duplicate write.
    * **circuit breaker** — "should this call be attempted at all?" When the
      breaker is open the call is **refused without being made**
      (:class:`CircuitOpenError`), so a dead dependency is not hammered.

    Every failure that survives the retries reaches the breaker: an error is
    therefore never turned into a false success, and when the retries are
    exhausted the last error is raised as-is — the caller sees what really
    happened, not a generic wrapper.

    The breaker counts **logically failed calls**, not attempts. A retry that
    succeeds is a healthy dependency; letting every attempt increment the
    counter would open the circuit *on the very retry it was meant to survive*,
    and a single flake would look like an outage. Only a call that failed every
    attempt counts once as a failure, and a call that succeeded records one
    success (which resets the consecutive counter).
    """
    breaker = (breaker_registry or registry).get(scope)
    wait = sleep or asyncio.sleep
    last_error: BaseException | None = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        if not breaker.allow():
            raise CircuitOpenError(scope)
        try:
            result = await call()
        except Exception as error:  # noqa: BLE001 - the breaker must see every failure
            last_error = error
            if attempt >= max_attempts:
                break
            if base_delay_seconds:
                await wait(base_delay_seconds * (2 ** (attempt - 1)))
            continue
        breaker.record_success()
        return result
    if last_error is not None:
        breaker.record_failure()
        raise last_error
    raise CircuitOpenError(scope)


def guard_sync(
    scope: str,
    call: Callable[[], T],
    *,
    breaker_registry: CircuitBreakerRegistry | None = None,
    max_attempts: int = 1,
) -> T:
    """Synchronous twin of :func:`guard` for the blocking object-store client.

    Same contract as :func:`guard`, including the counting rule: the breaker sees
    one failure per **call** that failed every attempt, and one success per call
    that succeeded. ``max_attempts`` defaults to 1 because an upload is a write:
    the breaker protects it, the retry stays for the repeatable reads.
    """
    breaker = (breaker_registry or registry).get(scope)
    last_error: BaseException | None = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        if not breaker.allow():
            raise CircuitOpenError(scope)
        try:
            result = call()
        except Exception as error:  # noqa: BLE001 - the breaker must see every failure
            last_error = error
            if attempt >= max_attempts:
                break
            continue
        breaker.record_success()
        return result
    if last_error is not None:
        breaker.record_failure()
        raise last_error
    raise CircuitOpenError(scope)


class CircuitBreakerRegistry:
    """Scope-keyed collection of breakers (§41.8: per connector, provider, agent).

    Args:
        default_config: thresholds applied to breakers created without an
            explicit config.
        clock: injectable monotonic clock shared by every breaker created
            through this registry.
    """

    def __init__(
        self,
        default_config: CircuitBreakerConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._default_config = default_config or DEFAULT_CIRCUIT_BREAKER_CONFIG
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    @property
    def default_config(self) -> CircuitBreakerConfig:
        """Thresholds applied to newly created breakers."""
        return self._default_config

    def get(
        self,
        scope: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Return (creating if needed) the breaker protecting *scope*."""
        if not scope or not isinstance(scope, str):
            raise ValueError("scope must be a non-empty string")
        breaker = self._breakers.get(scope)
        if breaker is None:
            breaker = CircuitBreaker(
                scope, config or self._default_config, clock=self._clock
            )
            self._breakers[scope] = breaker
        return breaker

    def states(self) -> dict[str, str]:
        """Return ``{scope: "open" | "closed" | "half_open"}`` for health."""
        return {scope: breaker.state.value for scope, breaker in self._breakers.items()}

    def snapshot(self) -> list[dict[str, Any]]:
        """Return the full JSON projection of every breaker (health/debug)."""
        return [breaker.to_dict() for breaker in self._breakers.values()]

    def reset(
        self,
        default_config: CircuitBreakerConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Drop every breaker (test helper); optionally reconfigure defaults."""
        self._breakers.clear()
        if default_config is not None:
            self._default_config = default_config
        if clock is not None:
            self._clock = clock


#: Process-wide registry surfaced by ``/v1/health`` (§41.8).
registry = CircuitBreakerRegistry()

__all__ = [
    "DEFAULT_CIRCUIT_BREAKER_CONFIG",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "registry",
]


