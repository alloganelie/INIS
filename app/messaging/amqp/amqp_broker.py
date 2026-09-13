"""AMQP broker implementing the MessageBroker interface per §4.4.

Uses ``aio-pika`` for the real connection. All network access happens
inside :meth:`AMQPBroker.connect`, :meth:`AMQPBroker.publish` and
:meth:`AMQPBroker.subscribe` so unit tests can mock ``aio-pika``
without a live RabbitMQ.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

import aio_pika

from app.core.errors import InfrastructureError
from app.messaging.amqp.topology import EXCHANGE_NAME
from app.messaging.amqp.topology import EXCHANGE_TYPE
from app.messaging.amqp.topology import MAIN_QUEUE
from app.messaging.amqp.topology import declare_topology

Envelope = dict[str, Any]
MessageHandler = Callable[[Envelope], Awaitable[None]]


class AMQPBroker:
    """MessageBroker over RabbitMQ via aio-pika (§4.4).

    Interface::

        async def publish(self, routing_key: str, message: Envelope) -> None
        async def subscribe(self, queue: str, handler: MessageHandler) -> None
    """

    def __init__(self, url: str = "amqp://guest:guest@localhost:5672/") -> None:
        self._url = url
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    @property
    def is_connected(self) -> bool:
        """Return True when a live connection is held."""
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        """Open the connection and declare the topology (idempotent)."""
        try:
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=10)
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME, type=EXCHANGE_TYPE, durable=True
            )
            topology = declare_topology()
            for queue_decl in topology.queues:
                await self._channel.declare_queue(
                    queue_decl.name,
                    durable=queue_decl.durable,
                    arguments=dict(queue_decl.arguments),
                )
            main = await self._channel.get_queue(MAIN_QUEUE)
            for binding in topology.bindings:
                if binding.queue == MAIN_QUEUE:
                    await main.bind(self._exchange, routing_key=binding.routing_key)
        except Exception as exc:
            raise InfrastructureError(f"AMQP connect failed: {exc}") from exc

    async def close(self) -> None:
        """Close the connection if open (never raises fatally)."""
        try:
            if self._connection is not None and not self._connection.is_closed:
                await self._connection.close()
        except Exception:
            pass
        finally:
            self._connection = None
            self._channel = None
            self._exchange = None

    async def _ensure_ready(self) -> None:
        if self._channel is None or self._exchange is None or not self.is_connected:
            await self.connect()

    async def publish(self, routing_key: str, message: Envelope) -> None:
        """Publish an envelope with the given routing key (§4.4)."""
        if not routing_key or not isinstance(routing_key, str):
            raise ValueError("routing_key must be a non-empty string")
        if not isinstance(message, dict):
            raise ValueError("message must be an envelope dict")
        await self._ensure_ready()
        assert self._channel is not None and self._exchange is not None
        try:
            body = json.dumps(message).encode("utf-8")
            amqp_message = aio_pika.Message(
                body=body,
                content_type="application/json",
                message_id=str(message.get("message_id", "")),
                correlation_id=str(message.get("correlation_id", "")),
            )
            await self._exchange.publish(amqp_message, routing_key=routing_key)
        except Exception as exc:
            raise InfrastructureError(f"AMQP publish failed: {exc}") from exc

    async def subscribe(self, queue: str, handler: MessageHandler) -> None:
        """Consume ``queue`` and await ``handler`` per message (ack on success)."""
        if not queue or not isinstance(queue, str):
            raise ValueError("queue must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        await self._ensure_ready()
        assert self._channel is not None
        try:
            amqp_queue = await self._channel.declare_queue(queue, durable=True)

            async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
                async with message.process(requeue=False):
                    envelope: Envelope = json.loads(message.body.decode("utf-8"))
                    await handler(envelope)

            await amqp_queue.consume(_on_message)
        except Exception as exc:
            raise InfrastructureError(f"AMQP subscribe failed: {exc}") from exc
