"""Helper to publish an Envelope on the AMQP broker (§5.1, §5.2).

Routing rule: the routing key IS the envelope ``message_type`` so the
topology bindings (one per V1 type) route the message to
``inis.messages``. Validation is explicit; no message is sent when the
envelope is invalid.
"""

from __future__ import annotations

from typing import Any
from typing import Protocol

from app.core.errors import ValidationError
from app.messaging.amqp.topology import routing_key_for
from app.messaging.protocol.envelope_validator import validate

Envelope = dict[str, Any]


class _Publisher(Protocol):
    async def publish(self, routing_key: str, message: Envelope) -> None: ...


async def publish_envelope(broker: _Publisher, envelope: Envelope) -> str:
    """Validate then publish an envelope; return the routing key used.

    Args:
        broker: Any object exposing ``publish(routing_key, message)``.
        envelope: Envelope dict per §5.1.

    Returns:
        The routing key used (envelope ``message_type``).

    Raises:
        ValidationError: If the envelope fails §5.1/§5.2 validation.
    """
    if not isinstance(envelope, dict):
        raise ValidationError("Envelope must be a dictionary")
    validate(envelope)
    message_type = envelope.get("message_type")
    if not isinstance(message_type, str):
        raise ValidationError("message_type is required and must be a string")
    routing_key = routing_key_for(message_type)
    await broker.publish(routing_key, envelope)
    return routing_key
