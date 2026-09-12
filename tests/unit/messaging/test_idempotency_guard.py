"""Tests for IdempotencyGuard per §5.3."""

import pytest

from app.messaging.protocol.idempotency_guard import IdempotencyGuard


class TestIdempotencyGuard:
    """Tests for IdempotencyGuard class."""

    def test_remember_and_get(self) -> None:
        """Test storing and retrieving a response."""
        guard = IdempotencyGuard()
        message_id = "MSG_01ABCDEFGHIJKLMNOPQRSTUV"
        response = {"status": "success", "data": "test"}

        guard.remember(message_id, response)
        retrieved = guard.get(message_id)

        assert retrieved == response

    def test_get_returns_none_for_unknown(self) -> None:
        """Test that get returns None for unknown message_id."""
        guard = IdempotencyGuard()

        result = guard.get("MSG_UNKNOWN01ABCDEFGHIJKLMNOP")

        assert result is None

    def test_has_returns_true_for_stored(self) -> None:
        """Test that has returns True for stored message_id."""
        guard = IdempotencyGuard()
        message_id = "MSG_01ABCDEFGHIJKLMNOPQRSTUV"

        guard.remember(message_id, {"data": "test"})

        assert guard.has(message_id) is True

    def test_has_returns_false_for_unknown(self) -> None:
        """Test that has returns False for unknown message_id."""
        guard = IdempotencyGuard()

        assert guard.has("MSG_UNKNOWN01ABCDEFGHIJKLMNOP") is False

    def test_overwrite_existing(self) -> None:
        """Test that remember overwrites existing response."""
        guard = IdempotencyGuard()
        message_id = "MSG_01ABCDEFGHIJKLMNOPQRSTUV"

        guard.remember(message_id, {"version": 1})
        guard.remember(message_id, {"version": 2})

        assert guard.get(message_id) == {"version": 2}

    def test_clear_removes_all(self) -> None:
        """Test that clear removes all stored responses."""
        guard = IdempotencyGuard()

        guard.remember("MSG_01ABCDEFGHIJKLMNOPQRSTUV", {"a": 1})
        guard.remember("MSG_02BCDEFGHIJKLMNOPQRSTUVW", {"b": 2})
        guard.clear()

        assert guard.get("MSG_01ABCDEFGHIJKLMNOPQRSTUV") is None
        assert guard.get("MSG_02BCDEFGHIJKLMNOPQRSTUVW") is None
        assert len(guard) == 0

    def test_len_returns_count(self) -> None:
        """Test that len returns the number of stored messages."""
        guard = IdempotencyGuard()

        assert len(guard) == 0

        guard.remember("MSG_01ABCDEFGHIJKLMNOPQRSTUV", {"a": 1})
        assert len(guard) == 1

        guard.remember("MSG_02BCDEFGHIJKLMNOPQRSTUVW", {"b": 2})
        assert len(guard) == 2

    def test_remember_rejects_non_string_message_id(self) -> None:
        """Test that remember rejects non-string message_id."""
        guard = IdempotencyGuard()

        with pytest.raises(TypeError, match="message_id must be a string"):
            guard.remember(123, {"data": "test"})

    def test_remember_rejects_invalid_prefix(self) -> None:
        """Test that remember rejects message_id without MSG_ prefix."""
        guard = IdempotencyGuard()

        with pytest.raises(ValueError, match="message_id must start with 'MSG_'"):
            guard.remember("CORR_01ABCDEFGHIJKLMNOPQRSTUV", {"data": "test"})

    def test_get_rejects_non_string_message_id(self) -> None:
        """Test that get rejects non-string message_id."""
        guard = IdempotencyGuard()

        with pytest.raises(TypeError, match="message_id must be a string"):
            guard.get(123)

    def test_has_rejects_non_string_message_id(self) -> None:
        """Test that has rejects non-string message_id."""
        guard = IdempotencyGuard()

        with pytest.raises(TypeError, match="message_id must be a string"):
            guard.has(123)

    def test_store_complex_response(self) -> None:
        """Test storing complex response objects."""
        guard = IdempotencyGuard()
        message_id = "MSG_01ABCDEFGHIJKLMNOPQRSTUV"
        response = {
            "status": "SUCCESS",
            "payload": {
                "items": [1, 2, 3],
                "nested": {"key": "value"},
            },
            "metadata": ["a", "b", "c"],
        }

        guard.remember(message_id, response)
        retrieved = guard.get(message_id)

        assert retrieved == response