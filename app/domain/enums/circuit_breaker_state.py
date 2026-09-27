"""Circuit breaker states: open | closed | half_open (§41.8)."""

from enum import Enum


class CircuitBreakerState(str, Enum):
    """Allowed circuit breaker states, exposed verbatim in ``/v1/health``."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
