"""Retry / dead-letter policy per §41.8 (pure logic, no I/O).

Implements the ``retry_policy`` structure from the spec:

- ``max_attempts``: total tries including the first attempt.
- ``initial_delay_ms``: delay before the first retry.
- ``backoff_multiplier``: exponential factor applied per attempt.
- ``max_delay_ms``: cap applied to every computed delay.
- ``retryable_errors``: error codes eligible for retry
  (default: SOURCE_UNAVAILABLE, TOOL_FAILURE, TIMEOUT).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Literal

NextAction = Literal["retry", "dead_letter"]

DEFAULT_RETRYABLE_ERRORS: frozenset[str] = frozenset(
    {"SOURCE_UNAVAILABLE", "TOOL_FAILURE", "TIMEOUT"}
)


@dataclass(frozen=True)
class RetryPolicy:
    """Immutable retry configuration (§41.8)."""

    max_attempts: int = 5
    initial_delay_ms: int = 1000
    backoff_multiplier: float = 2.0
    max_delay_ms: int = 30000
    retryable_errors: frozenset[str] = field(default_factory=lambda: DEFAULT_RETRYABLE_ERRORS)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_delay_ms < 0:
            raise ValueError("initial_delay_ms must be >= 0")
        if self.backoff_multiplier < 1.0:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if self.max_delay_ms < 0:
            raise ValueError("max_delay_ms must be >= 0")


DEFAULT_RETRY_POLICY = RetryPolicy()


def compute_delay_ms(attempt: int, policy: RetryPolicy = DEFAULT_RETRY_POLICY) -> int:
    """Return the backoff delay for ``attempt`` (1-indexed, pure).

    ``attempt`` is the number of the attempt that just failed:
    attempt=1 -> ``initial_delay_ms``,
    attempt=2 -> ``initial_delay_ms * multiplier``, etc.
    The result is capped at ``max_delay_ms``.

    Raises:
        ValueError: If ``attempt`` < 1.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = float(policy.initial_delay_ms) * (policy.backoff_multiplier ** (attempt - 1))
    return min(int(delay), policy.max_delay_ms)


def should_retry(
    error_code: str,
    attempt: int,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> bool:
    """Return True when another attempt is allowed (pure).

    Retry happens only when the error is retryable AND ``attempt``
    (just failed) is strictly below ``max_attempts``.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if error_code not in policy.retryable_errors:
        return False
    return attempt < policy.max_attempts


def next_action(
    error_code: str,
    attempt: int,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> tuple[NextAction, int | None]:
    """Return ``("retry", delay_ms)`` or ``("dead_letter", None)`` (pure)."""
    if should_retry(error_code, attempt, policy):
        return ("retry", compute_delay_ms(attempt, policy))
    return ("dead_letter", None)


class DeadLetterHandler:
    """State-free helper binding a :class:`RetryPolicy` to pure helpers."""

    def __init__(self, policy: RetryPolicy = DEFAULT_RETRY_POLICY) -> None:
        self._policy = policy

    @property
    def policy(self) -> RetryPolicy:
        """Return the configured retry policy."""
        return self._policy

    def compute_delay(self, attempt: int) -> int:
        """Return the backoff delay for ``attempt`` (1-indexed)."""
        return compute_delay_ms(attempt, self._policy)

    def should_retry(self, error_code: str, attempt: int) -> bool:
        """Return True when another attempt is allowed."""
        return should_retry(error_code, attempt, self._policy)

    def next_action(self, error_code: str, attempt: int) -> tuple[NextAction, int | None]:
        """Return ``("retry", delay_ms)`` or ``("dead_letter", None)``."""
        return next_action(error_code, attempt, self._policy)
