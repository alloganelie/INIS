"""Resilience patterns: circuit breaker + retry policy (§41.8).

The retry policy (``RetryPolicy``, backoff, dead-letter) has its canonical
implementation in :mod:`app.messaging.amqp.dead_letter_handler` and is
re-exported here so connectors share one import site for §41.8.
"""

from app.connectors.resilience.circuit_breaker import CircuitBreaker
from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
from app.connectors.resilience.circuit_breaker import CircuitBreakerRegistry
from app.connectors.resilience.circuit_breaker import CircuitOpenError
from app.connectors.resilience.circuit_breaker import registry
from app.messaging.amqp.dead_letter_handler import DEFAULT_RETRYABLE_ERRORS
from app.messaging.amqp.dead_letter_handler import RetryPolicy
from app.messaging.amqp.dead_letter_handler import compute_delay_ms
from app.messaging.amqp.dead_letter_handler import should_retry

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "DEFAULT_RETRYABLE_ERRORS",
    "RetryPolicy",
    "compute_delay_ms",
    "registry",
    "should_retry",
]