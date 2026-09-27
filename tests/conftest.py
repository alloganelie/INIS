"""Global test fixtures."""

import pytest

from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
from app.connectors.resilience.circuit_breaker import registry as breaker_registry


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    """Isolate the process-wide §41.8 breaker registry between tests."""
    breaker_registry.reset(default_config=CircuitBreakerConfig())
    yield
    breaker_registry.reset(default_config=CircuitBreakerConfig())
