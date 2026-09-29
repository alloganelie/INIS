"""§4.4/§5.2 — the AMQP broker: topology, publishing and consumption.

Two modes, so the test is useful everywhere and authoritative in CI:

* the **transport tests** below run the real :class:`AMQPBroker` against an
  in-process AMQP double, covering every code path the broker owns — topology
  declaration, envelope serialisation, handler dispatch and ack semantics;
* the **live broker tests** (``INIS_RABBITMQ_URL``) run the same broker against
  a real RabbitMQ, which is what ``docker compose --profile messaging``
  provides. They skip when no broker is configured so the suite stays runnable
  without one, and they are the tests that prove the contract holds over the
  wire.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from app.core.errors import InfrastructureError
from app.messaging.amqp import amqp_broker as broker_module
from app.messaging.amqp.amqp_broker import AMQPBroker
from app.messaging.amqp.topology import DLQ_QUEUE, EXCHANGE_NAME, MAIN_QUEUE
from app.messaging.amqp.topology import MESSAGE_ROUTING_KEYS
from app.messaging.protocol.envelope_builder import VALID_MESSAGE_TYPES

#: RabbitMQ endpoint of the local compose stack, when one is running.
LIVE_BROKER_ENV = "INIS_RABBITMQ_URL"

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# In-process AMQP double (the aio-pika surface AMQPBroker uses)
# ---------------------------------------------------------------------------
class FakeMessage:
    """Stand-in for ``aio_pika.Message``."""

    def __init__(
        self,
        body: bytes,
        content_type: str | None = None,
        message_id: str = "",
        correlation_id: str = "",
    ) -> None:
        self.body = body
        self.content_type = content_type
        self.message_id = message_id
        self.correlation_id = correlation_id

    def envelope(self) -> dict[str, Any]:
        """Return the decoded envelope body."""
        return json.loads(self.body.decode("utf-8"))


class FakeIncomingMessage:
    """Stand-in for ``aio_pika.IncomingMessage`` with ack bookkeeping."""

    def __init__(self, envelope: dict[str, Any]) -> None:
        self.body = json.dumps(envelope).encode("utf-8")
        self.acked = False
        self.nacked = False
        self.requeue: bool | None = None

    def process(self, requeue: bool = True) -> Any:
        """Return the ``async with`` context implementing ack/nack."""
        outer = self

        class _Process:
            async def __aenter__(self) -> "FakeIncomingMessage":
                return outer

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
                if exc_type is None:
                    outer.acked = True
                else:
                    outer.nacked = True
                    outer.requeue = requeue
                return False

        return _Process()


class FakeExchange:
    """Stand-in for ``aio_pika.Exchange``."""

    def __init__(self, name: str, type: str, durable: bool) -> None:
        self.name = name
        self.type = type
        self.durable = durable
        self.published: list[tuple[str, FakeMessage]] = []

    async def publish(self, message: FakeMessage, routing_key: str) -> None:
        """Record a publication."""
        self.published.append((routing_key, message))


class FakeQueue:
    """Stand-in for ``aio_pika.Queue``."""

    def __init__(self, name: str, durable: bool = True) -> None:
        self.name = name
        self.durable = durable
        self.bindings: list[str] = []
        self.consumer: Any = None

    async def bind(self, exchange: Any, routing_key: str) -> None:
        """Record a binding."""
        self.bindings.append(routing_key)

    async def consume(self, callback: Any) -> None:
        """Register the consumer callback."""
        self.consumer = callback

    async def deliver(self, envelope: dict[str, Any]) -> FakeIncomingMessage:
        """Feed one envelope to the registered consumer."""
        assert self.consumer is not None, "no consumer registered on this queue"
        message = FakeIncomingMessage(envelope)
        await self.consumer(message)
        return message


class FakeChannel:
    """Stand-in for ``aio_pika.Channel``."""

    def __init__(self) -> None:
        self.prefetch_count: int | None = None
        self.exchanges: dict[str, FakeExchange] = {}
        self.queues: dict[str, FakeQueue] = {}

    async def set_qos(self, prefetch_count: int) -> None:
        """Record the prefetch window."""
        self.prefetch_count = prefetch_count

    async def declare_exchange(
        self, name: str, type: str = "topic", durable: bool = True
    ) -> FakeExchange:
        """Declare (idempotently) an exchange."""
        if name not in self.exchanges:
            self.exchanges[name] = FakeExchange(name, type, durable)
        return self.exchanges[name]

    async def declare_queue(
        self, name: str, durable: bool = True, arguments: dict[str, Any] | None = None
    ) -> FakeQueue:
        """Declare (idempotently) a queue."""
        if name not in self.queues:
            self.queues[name] = FakeQueue(name, durable)
        return self.queues[name]

    async def get_queue(self, name: str) -> FakeQueue:
        """Return an already declared queue."""
        return self.queues[name]


class FakeConnection:
    """Stand-in for ``aio_pika.RobustConnection``."""

    def __init__(self) -> None:
        self.is_closed = False
        self.channel_instance = FakeChannel()

    async def channel(self) -> FakeChannel:
        """Return the single channel of this connection."""
        return self.channel_instance

    async def close(self) -> None:
        """Mark the connection closed."""
        self.is_closed = True


class FakeAioPika:
    """The subset of ``aio_pika`` that :class:`AMQPBroker` uses."""

    Message = FakeMessage

    def __init__(self, fail_on_connect: bool = False) -> None:
        self.fail_on_connect = fail_on_connect
        self.urls: list[str] = []
        self.connection = FakeConnection()

    async def connect_robust(self, url: str) -> FakeConnection:
        """Return a fake connection, or fail when asked to."""
        self.urls.append(url)
        if self.fail_on_connect:
            raise OSError("connection refused")
        return self.connection


@pytest.fixture
def fake_pika(monkeypatch: pytest.MonkeyPatch) -> FakeAioPika:
    """Install the in-process AMQP double in place of ``aio_pika``."""
    fake = FakeAioPika()
    monkeypatch.setattr(broker_module, "aio_pika", fake)
    return fake


@pytest.fixture
def broker(fake_pika: FakeAioPika) -> AMQPBroker:
    """Return a broker whose transport is the in-process double."""
    return AMQPBroker("amqp://guest:guest@localhost:5672/")


def _envelope(message_type: str) -> dict[str, Any]:
    """Return a minimal §5.1 envelope of *message_type*."""
    return {
        "message_id": "MSG_01ARZ3NDEKTSV4RRFFQ69G5F77",
        "correlation_id": "CORR_01ARZ3NDEKTSV4RRFFQ69G5F88",
        "message_type": message_type,
        "protocol_version": "1.0",
        "payload": {"objective": "capitale de la France"},
    }


class TestTransportContract:
    """§4.4 — the broker declares the topology, then routes envelopes."""

    async def test_broker_starts_disconnected(self, broker: AMQPBroker) -> None:
        """No connection is opened before it is needed."""
        assert broker.is_connected is False

    async def test_connect_declares_the_section_5_2_topology(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """Exchange, both queues, one binding per V1 message type and the QoS."""
        await broker.connect()
        channel = fake_pika.connection.channel_instance

        assert broker.is_connected is True
        assert fake_pika.urls == ["amqp://guest:guest@localhost:5672/"]
        assert channel.prefetch_count == 10
        assert channel.exchanges[EXCHANGE_NAME].type == "topic"
        assert set(channel.queues) == {MAIN_QUEUE, DLQ_QUEUE}
        assert sorted(channel.queues[MAIN_QUEUE].bindings) == sorted(MESSAGE_ROUTING_KEYS)
        assert set(MESSAGE_ROUTING_KEYS) == set(VALID_MESSAGE_TYPES)

    async def test_connect_failure_is_an_infrastructure_error(
        self, broker: AMQPBroker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broker that cannot be reached is reported, never swallowed."""
        monkeypatch.setattr(broker_module, "aio_pika", FakeAioPika(fail_on_connect=True))

        with pytest.raises(InfrastructureError, match="AMQP connect failed"):
            await broker.connect()

    async def test_publish_serialises_the_envelope(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """The routing key is the message type and the body is the envelope."""
        message_type = MESSAGE_ROUTING_KEYS[0]
        envelope = _envelope(message_type)

        await broker.publish(message_type, envelope)

        exchange = fake_pika.connection.channel_instance.exchanges[EXCHANGE_NAME]
        routing_key, message = exchange.published[-1]
        assert routing_key == message_type
        assert message.content_type == "application/json"
        assert message.message_id == envelope["message_id"]
        assert message.correlation_id == envelope["correlation_id"]
        assert message.envelope() == envelope

    @pytest.mark.parametrize(
        ("routing_key", "message"),
        [("", {}), ("task.assignment", "not-an-envelope"), ("task.assignment", None)],
    )
    async def test_publish_refuses_invalid_arguments(
        self,
        broker: AMQPBroker,
        fake_pika: FakeAioPika,
        routing_key: str,
        message: Any,
    ) -> None:
        """A malformed publication fails fast, without touching the network."""
        with pytest.raises(ValueError):
            await broker.publish(routing_key, message)

        assert fake_pika.urls == []

    async def test_subscribe_dispatches_and_acks(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """A consumed envelope reaches the handler as a decoded mapping."""
        received: list[dict[str, Any]] = []

        async def handler(envelope: dict[str, Any]) -> None:
            received.append(envelope)

        await broker.subscribe(MAIN_QUEUE, handler)
        queue = fake_pika.connection.channel_instance.queues[MAIN_QUEUE]
        envelope = _envelope(MESSAGE_ROUTING_KEYS[1])

        message = await queue.deliver(envelope)

        assert received == [envelope]
        assert message.acked is True

    async def test_failing_handler_leaves_the_message_unacked(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """§5.3 — a handler error must not ack the message away."""

        async def handler(envelope: dict[str, Any]) -> None:
            raise RuntimeError("handler exploded")

        await broker.subscribe(MAIN_QUEUE, handler)
        queue = fake_pika.connection.channel_instance.queues[MAIN_QUEUE]
        message = FakeIncomingMessage(_envelope(MESSAGE_ROUTING_KEYS[2]))

        with pytest.raises(RuntimeError):
            await queue.consumer(message)

        assert message.acked is False
        assert message.nacked is True
        assert message.requeue is False

    @pytest.mark.parametrize("queue_name", ["", None])
    async def test_subscribe_refuses_a_missing_queue(
        self, broker: AMQPBroker, fake_pika: FakeAioPika, queue_name: Any
    ) -> None:
        """Subscribing without a queue is a programming error, not a no-op."""
        with pytest.raises(ValueError):
            await broker.subscribe(queue_name, lambda envelope: None)

        assert fake_pika.urls == []

    async def test_subscribe_refuses_a_non_callable_handler(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """A handler that cannot be awaited must be rejected."""
        with pytest.raises(ValueError):
            await broker.subscribe(MAIN_QUEUE, "not-callable")

        assert fake_pika.urls == []

    async def test_close_releases_the_connection(
        self, broker: AMQPBroker, fake_pika: FakeAioPika
    ) -> None:
        """``close`` is idempotent and leaves the broker reusable."""
        await broker.connect()
        await broker.close()

        assert broker.is_connected is False
        assert fake_pika.connection.is_closed is True

        await broker.close()
        assert broker.is_connected is False


@pytest.mark.skipif(
    not os.environ.get(LIVE_BROKER_ENV),
    reason=f"{LIVE_BROKER_ENV} not configured (docker compose --profile messaging)",
)
class TestLiveBroker:
    """§4.4 — the same contract over a real RabbitMQ."""

    async def test_envelope_round_trips_through_rabbitmq(self) -> None:
        """A published envelope is consumed by a subscriber, intact."""
        import asyncio

        live = AMQPBroker(os.environ[LIVE_BROKER_ENV])
        received: list[dict[str, Any]] = []
        delivered = asyncio.Event()

        async def handler(envelope: dict[str, Any]) -> None:
            received.append(envelope)
            delivered.set()

        message_type = MESSAGE_ROUTING_KEYS[0]
        envelope = _envelope(message_type)
        try:
            await live.connect()
            await live.subscribe(MAIN_QUEUE, handler)
            await live.publish(message_type, envelope)
            await asyncio.wait_for(delivered.wait(), timeout=15)
        finally:
            await live.close()

        assert envelope in received

