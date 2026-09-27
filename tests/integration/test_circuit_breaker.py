"""Integration tests for the §41.8 retry / circuit-breaker policy.

The breaker is driven with an injectable clock, so every transition
(``closed -> open -> half_open -> closed``) is asserted without sleeping, and
the registry is asserted to expose the states ``/v1/health`` publishes.
"""

from __future__ import annotations

import pytest

from app.connectors.resilience.circuit_breaker import (
    DEFAULT_CIRCUIT_BREAKER_CONFIG,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitOpenError,
)
from app.domain.enums.circuit_breaker_state import CircuitBreakerState


class FakeClock:
    """Monotonic clock under test control."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move time forward."""
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    """Return a controllable clock."""
    return FakeClock()


@pytest.fixture
def breaker(clock: FakeClock) -> CircuitBreaker:
    """Return a breaker with a 2-failure threshold and a 10 s timeout."""
    return CircuitBreaker(
        "provider:test",
        CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_seconds=10, half_open_max_calls=1
        ),
        clock=clock,
    )


class TestClosedState:
    """§41.8 — a healthy dependency stays closed."""

    def test_starts_closed(self, breaker: CircuitBreaker) -> None:
        """A fresh breaker is closed and allows calls."""
        assert breaker.state is CircuitBreakerState.CLOSED
        assert breaker.allow() is True
        assert breaker.failure_count == 0

    def test_successes_keep_it_closed(self, breaker: CircuitBreaker) -> None:
        """Successes never open the breaker."""
        for _ in range(10):
            breaker.record_success()
        assert breaker.state is CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    def test_failure_below_threshold_stays_closed(
        self, breaker: CircuitBreaker
    ) -> None:
        """One failure with a threshold of two is not enough to open."""
        breaker.record_failure()
        assert breaker.state is CircuitBreakerState.CLOSED
        assert breaker.failure_count == 1
        assert breaker.allow() is True

    def test_success_resets_the_failure_count(self, breaker: CircuitBreaker) -> None:
        """Consecutive failures are the criterion, so a success clears them."""
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        assert breaker.state is CircuitBreakerState.CLOSED
        assert breaker.failure_count == 1


class TestOpenState:
    """§41.8 — reaching the threshold opens the circuit."""

    def test_threshold_opens_the_breaker(self, breaker: CircuitBreaker) -> None:
        """Two consecutive failures open the breaker."""
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state is CircuitBreakerState.OPEN

    def test_open_breaker_refuses_calls(self, breaker: CircuitBreaker) -> None:
        """An open breaker refuses every call (fail fast, no retry storm)."""
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.allow() is False

    async def test_run_raises_circuit_open_error(self, breaker: CircuitBreaker) -> None:
        """``run`` refuses to invoke the dependency while open."""
        breaker.record_failure()
        breaker.record_failure()
        called = False

        async def _call() -> str:
            nonlocal called
            called = True
            return "ok"

        with pytest.raises(CircuitOpenError) as excinfo:
            await breaker.run(_call)
        assert called is False
        assert excinfo.value.scope == "provider:test"

    def test_stale_success_does_not_cancel_recovery(
        self, breaker: CircuitBreaker
    ) -> None:
        """A success from an in-flight call must not close an open breaker."""
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        assert breaker.state is CircuitBreakerState.OPEN

