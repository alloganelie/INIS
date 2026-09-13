"""Optional MQTT broker for light events / telemetry per §4.4 (stub).

``paho-mqtt`` is intentionally imported lazily so unit tests and
environments without the optional dependency can import this module
safely. Real network use raises an explicit error when the library is
missing instead of failing at import time.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from app.core.errors import InfrastructureError

Envelope = dict[str, Any]
MessageHandler = Callable[[Envelope], Awaitable[None]]


class MQTTBroker:
    """Minimal MQTT transport with the same publish/subscribe shape as AMQP."""

    def __init__(self, host: str = "localhost", port: int = 1883) -> None:
        self._host = host
        self._port = port
        self._handlers: dict[str, MessageHandler] = {}
        self._client: Any | None = None

    @property
    def is_connected(self) -> bool:
        """Return True when an MQTT client session is held."""
        return self._client is not None

    def _require_client(self) -> Any:
        try:
            from paho.mqtt import client as mqtt_client
        except ImportError as exc:
            raise InfrastructureError(
                "paho-mqtt is not installed; MQTT transport is unavailable"
            ) from exc
        if self._client is None:
            self._client = mqtt_client.Client()
        return self._client

    async def publish(self, topic: str, message: Envelope) -> None:
        """Publish an envelope as JSON on ``topic`` (stub: lazy client)."""
        if not topic or not isinstance(topic, str):
            raise ValueError("topic must be a non-empty string")
        if not isinstance(message, dict):
            raise ValueError("message must be an envelope dict")
        client = self._require_client()
        try:
            client.publish(topic, json.dumps(message))
        except Exception as exc:
            raise InfrastructureError(f"MQTT publish failed: {exc}") from exc

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        """Record ``handler`` for ``topic`` without network I/O (stub)."""
        if not topic or not isinstance(topic, str):
            raise ValueError("topic must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._handlers[topic] = handler

    async def handle_message(self, topic: str, payload: Envelope) -> Any:
        """Dispatch a received payload to the handler of ``topic`` (stub)."""
        handler = self._handlers.get(topic)
        if handler is None:
            return None
        return await handler(payload)
