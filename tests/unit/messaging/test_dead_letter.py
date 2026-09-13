"""Tests for retry / dead-letter policy per §41.8 (pure logic, no I/O)."""

from app.messaging.amqp.dead_letter_handler import DeadLetterHandler
from app.messaging.amqp.dead_letter_handler import RetryPolicy


class TestDeadLetter:
    """4 tests covering backoff, max attempts, eligibility and cap."""

    def test_exponential_backoff(self) -> None:
        """Delays grow as initial * multiplier^(attempt-1)."""
        policy = RetryPolicy(
            max_attempts=5,
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            max_delay_ms=30000,
        )
        handler = DeadLetterHandler(policy)
        assert handler.compute_delay(1) == 1000
        assert handler.compute_delay(2) == 2000
        assert handler.compute_delay(3) == 4000

    def test_max_attempts_sends_to_dead_letter(self) -> None:
        """At max_attempts the message goes to the DLQ, not retry."""
        handler = DeadLetterHandler(RetryPolicy(max_attempts=3))
        assert handler.next_action("TIMEOUT", 1)[0] == "retry"
        assert handler.next_action("TIMEOUT", 2)[0] == "retry"
        action, delay = handler.next_action("TIMEOUT", 3)
        assert action == "dead_letter"
        assert delay is None

    def test_non_retryable_error_goes_to_dead_letter(self) -> None:
        """VALIDATION_ERROR is not retryable even on first attempt."""
        handler = DeadLetterHandler()
        assert handler.should_retry("TIMEOUT", 1) is True
        assert handler.should_retry("VALIDATION_ERROR", 1) is False
        assert handler.next_action("VALIDATION_ERROR", 1)[0] == "dead_letter"

    def test_delay_capped_at_max_delay(self) -> None:
        """Computed delays never exceed max_delay_ms."""
        handler = DeadLetterHandler(
            RetryPolicy(
                max_attempts=10,
                initial_delay_ms=1000,
                backoff_multiplier=10.0,
                max_delay_ms=5000,
            )
        )
        assert handler.compute_delay(4) == 5000
        action, delay = handler.next_action("TOOL_FAILURE", 1)
        assert action == "retry"
        assert delay is not None and delay <= 5000
