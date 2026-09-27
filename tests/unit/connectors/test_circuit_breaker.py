"""Unit tests for the §41.8 circuit breaker and its health exposure."""

import pytest

from app.connectors.resilience.circuit_breaker import CircuitBreaker
from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
from app.connectors.resilience.circuit_breaker import CircuitBreakerRegistry
from app.connectors.resilience.circuit_breaker import CircuitOpenError
from app.domain.enums.circuit_breaker_state import CircuitBreakerState

CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout_seconds=30,
    half_open_max_calls=2,
)


class FakeClock:
    """Deterministic monotonic clock for recovery-timeout transitions."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_breaker() -> CircuitBreaker:
    return CircuitBreaker("provider:test", CONFIG, clock=FakeClock())


def test_config_rejects_non_positive_thresholds() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreakerConfig(failure_threshold=0)
    with pytest.raises(ValueError, match="recovery_timeout_seconds"):
        CircuitBreakerConfig(recovery_timeout_seconds=0)
    with pytest.raises(ValueError, match="half_open_max_calls"):
        CircuitBreakerConfig(half_open_max_calls=0)


def test_config_to_dict_matches_the_spec_block() -> None:
    assert CircuitBreakerConfig().to_dict() == {
        "failure_threshold": 5,
        "recovery_timeout_seconds": 30,
        "half_open_max_calls": 2,
    }


def test_breaker_starts_closed_and_allows_calls() -> None:
    breaker = make_breaker()
    assert breaker.state is CircuitBreakerState.CLOSED
    assert breaker.allow() is True
    assert breaker.to_dict() == {
        "scope": "provider:test",
        "state": "closed",
        "failure_count": 0,
        "config": CONFIG.to_dict(),
    }


def test_failures_below_threshold_keep_it_closed() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold - 1):
        breaker.record_failure()
    assert breaker.state is CircuitBreakerState.CLOSED
    assert breaker.allow() is True
    assert breaker.failure_count == CONFIG.failure_threshold - 1


def test_breaker_opens_at_the_failure_threshold() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold):
        breaker.record_failure()
    assert breaker.state is CircuitBreakerState.OPEN
    assert breaker.allow() is False


def test_success_resets_the_consecutive_failure_count() -> None:
    breaker = make_breaker()
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.failure_count == 0
    assert breaker.state is CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_run_refuses_calls_while_open_and_records_failures() -> None:
    breaker = make_breaker()

    async def boom() -> str:
        raise TimeoutError("dependency down")

    for _ in range(CONFIG.failure_threshold):
        with pytest.raises(TimeoutError):
            await breaker.run(boom)
    assert breaker.state is CircuitBreakerState.OPEN

    with pytest.raises(CircuitOpenError) as excinfo:
        await breaker.run(boom)
    assert excinfo.value.scope == "provider:test"

    async def ok() -> str:
        return "done"

    # The dependency being healthy again does not bypass an open breaker.
    with pytest.raises(CircuitOpenError):
        await breaker.run(ok)


def test_open_breaker_half_opens_after_recovery_timeout() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold):
        breaker.record_failure()
    clock = breaker._clock  # FakeClock captured at construction
    clock.advance(CONFIG.recovery_timeout_seconds - 1)
    assert breaker.state is CircuitBreakerState.OPEN
    clock.advance(1)
    assert breaker.state is CircuitBreakerState.HALF_OPEN


def test_half_open_success_closes_the_breaker() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold):
        breaker.record_failure()
    breaker._clock.advance(CONFIG.recovery_timeout_seconds)
    assert breaker.allow() is True  # reserves a probe slot
    breaker.record_success()
    assert breaker.state is CircuitBreakerState.CLOSED
    assert breaker.failure_count == 0


def test_half_open_failure_reopens_and_restarts_the_timer() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold):
        breaker.record_failure()
    clock = breaker._clock
    clock.advance(CONFIG.recovery_timeout_seconds)
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.state is CircuitBreakerState.OPEN
    # The recovery timer restarted: no immediate half-open transition.
    clock.advance(CONFIG.recovery_timeout_seconds - 1)
    assert breaker.state is CircuitBreakerState.OPEN


def test_half_open_limits_probes_to_half_open_max_calls() -> None:
    breaker = make_breaker()
    for _ in range(CONFIG.failure_threshold):
        breaker.record_failure()
    breaker._clock.advance(CONFIG.recovery_timeout_seconds)
    allowed = [breaker.allow() for _ in range(CONFIG.half_open_max_calls + 1)]
    assert allowed == [True] * CONFIG.half_open_max_calls + [False]


def test_registry_keys_breakers_per_scope_and_exposes_states() -> None:
    registry = CircuitBreakerRegistry(clock=FakeClock())
    provider = registry.get("provider:serper")
    connector = registry.get("connector:csv")
    assert provider is registry.get("provider:serper")
    assert provider is not connector

    provider.record_failure()
    assert registry.states() == {"provider:serper": "closed", "connector:csv": "closed"}
    for _ in range(provider.config.failure_threshold):
        provider.record_failure()
    assert registry.states()["provider:serper"] == "open"
    assert "open" in registry.states().values()

    snapshot = {entry["scope"]: entry for entry in registry.snapshot()}
    assert snapshot["provider:serper"]["state"] == "open"
    assert snapshot["provider:serper"]["config"] == provider.config.to_dict()

    registry.reset()
    assert registry.states() == {}

    with pytest.raises(ValueError, match="scope"):
        registry.get("")


class _FailingProvider:
    provider_id = "flaky"

    async def search(self, query: str, limit: int) -> list:
        raise TimeoutError("provider down")


@pytest.mark.asyncio
async def test_provider_router_opens_its_breaker_after_consecutive_failures() -> None:
    from app.connectors.resilience.circuit_breaker import registry
    from app.connectors.web.provider_router import ProviderRouter

    registry.reset(default_config=CircuitBreakerConfig(failure_threshold=2))
    router = ProviderRouter(
        providers={"flaky": _FailingProvider()}, default_provider_id="flaky"
    )

    for _ in range(2):
        with pytest.raises(TimeoutError):
            await router.search("inis", 1)

    assert registry.states() == {"provider:flaky": "open"}
    with pytest.raises(CircuitOpenError):
        await router.search("inis", 1)

    # The breaker is still exposed per scope for §41.8 health reporting.
    assert "provider:flaky" in registry.states()

