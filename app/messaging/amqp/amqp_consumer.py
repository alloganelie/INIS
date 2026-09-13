"""AMQP consumer dispatching on ``message_type`` (§5.2).

The consumer validates every incoming envelope (§5.1) then routes it
to the handler registered for its ``message_type``. Messages with no
registered handler are ignored (returned as ``None``) so a missing
optional handler never crashes the worker loop.
"""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import Protocol

from app.core.errors import ValidationError
from app.messaging.amqp.topology import MAIN_QUEUE
from app.messaging.protocol.envelope_builder import VALID_MESSAGE_TYPES
from app.messaging.protocol.envelope_validator import validate

Envelope = dict[str, Any]
MessageHandler = Callable[[Envelope], Awaitable[None]]


class _Subscriber(Protocol):
    async def subscribe(self, queue: str, handler: MessageHandler) -> None: ...


class AMQPConsumer:
    """Dispatch envelopes to per-``message_type`` handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, MessageHandler] = {}

    def register_handler(self, message_type: str, handler: MessageHandler) -> None:
        """Register the handler for one V1 message type."""
        if message_type not in VALID_MESSAGE_TYPES:
            raise ValueError(f"Invalid message_type: {message_type}")
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._handlers[message_type] = handler

    @property
    def registered_types(self) -> tuple[str, ...]:
        """Return the sorted message types with a handler."""
        return tuple(sorted(self._handlers))

    async def handle_envelope(self, envelope: Envelope) -> Any:
        """Validate then dispatch; return the handler result (None if ignored)."""
        if not isinstance(envelope, dict):
            raise ValidationError("Envelope must be a dictionary")
        validate(envelope)
        message_type = envelope.get("message_type")
        handler = self._handlers.get(str(message_type))
        if handler is None:
            return None
        return await handler(envelope)

    async def run(self, broker: _Subscriber, queue: str = MAIN_QUEUE) -> None:
        """Subscribe to ``queue`` and dispatch via :meth:`handle_envelope`."""
        if not queue or not isinstance(queue, str):
            raise ValueError("queue must be a non-empty string")
        await broker.subscribe(queue, self.handle_envelope)
