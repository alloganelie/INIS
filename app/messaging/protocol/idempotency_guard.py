"""In-memory idempotency guard for INIS messaging per §5.3."""

from typing import Any


class IdempotencyGuard:
    """
    In-memory idempotency guard storing message_id -> response mapping.

    Per §5.3: message_id is unique. If a message already processed arrives,
    INIS returns the previous response if available, otherwise ignores.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def remember(self, message_id: str, response: Any) -> None:
        """
        Store a response for a message_id.

        Args:
            message_id: The MSG_ULID message identifier.
            response: The response to store (any serializable object).
        """
        if not isinstance(message_id, str):
            raise TypeError("message_id must be a string")
        if not message_id.startswith("MSG_"):
            raise ValueError("message_id must start with 'MSG_'")
        self._store[message_id] = response

    def get(self, message_id: str) -> Any | None:
        """
        Retrieve a previously stored response for a message_id.

        Args:
            message_id: The MSG_ULID message identifier.

        Returns:
            The stored response, or None if not found.
        """
        if not isinstance(message_id, str):
            raise TypeError("message_id must be a string")
        return self._store.get(message_id)

    def has(self, message_id: str) -> bool:
        """
        Check if a message_id has been processed.

        Args:
            message_id: The MSG_ULID message identifier.

        Returns:
            True if the message_id is in the store, False otherwise.
        """
        if not isinstance(message_id, str):
            raise TypeError("message_id must be a string")
        return message_id in self._store

    def clear(self) -> None:
        """Clear all stored responses (for testing)."""
        self._store.clear()

    def __len__(self) -> int:
        """Return the number of stored message_ids."""
        return len(self._store)