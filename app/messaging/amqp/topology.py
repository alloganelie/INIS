"""AMQP topology declarations for INIS messaging per §4.4 and §5.2.

Pure logic only: no I/O, no broker connection. The broker layer
(:mod:`app.messaging.amqp.amqp_broker`) consumes the declarations
returned by :func:`declare_topology` to declare exchanges, queues
and bindings at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from app.messaging.protocol.envelope_builder import VALID_MESSAGE_TYPES

EXCHANGE_NAME: str = "inis.topic"
EXCHANGE_TYPE: str = "topic"
MAIN_QUEUE: str = "inis.messages"
DLQ_QUEUE: str = "inis.messages.dlq"

#: Routing keys are exactly the V1 message types (§5.2).
MESSAGE_ROUTING_KEYS: tuple[str, ...] = tuple(sorted(VALID_MESSAGE_TYPES))


@dataclass(frozen=True)
class ExchangeDeclaration:
    """Pure description of the topic exchange to declare."""

    name: str = EXCHANGE_NAME
    type: str = EXCHANGE_TYPE
    durable: bool = True


@dataclass(frozen=True)
class QueueDeclaration:
    """Pure description of a queue to declare."""

    name: str
    durable: bool = True
    arguments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Binding:
    """Pure description of an exchange -> queue binding."""

    exchange: str
    queue: str
    routing_key: str


@dataclass(frozen=True)
class Topology:
    """Full set of declarations required by the AMQP broker."""

    exchange: ExchangeDeclaration
    queues: tuple[QueueDeclaration, ...]
    bindings: tuple[Binding, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable view of the topology."""
        return {
            "exchange": {
                "name": self.exchange.name,
                "type": self.exchange.type,
                "durable": self.exchange.durable,
            },
            "queues": [
                {"name": q.name, "durable": q.durable, "arguments": dict(q.arguments)}
                for q in self.queues
            ],
            "bindings": [
                {"exchange": b.exchange, "queue": b.queue, "routing_key": b.routing_key}
                for b in self.bindings
            ],
        }


def routing_key_for(message_type: str) -> str:
    """Return the routing key for a V1 message type (§5.2).

    The routing key IS the message_type so consumers can dispatch
    on it directly.

    Raises:
        ValueError: If the message_type is not part of V1.
    """
    if message_type not in VALID_MESSAGE_TYPES:
        raise ValueError(f"Invalid message_type: {message_type}")
    return message_type


def declare_topology() -> Topology:
    """Build the queue/exchange declarations (§5.2).

    - Main queue: ``inis.messages`` bound once per V1 message type.
    - DLQ queue: ``inis.messages.dlq`` receiving rejected messages.
    - The main queue advertises the DLQ via ``x-dead-letter`` args
      (interpreted by the broker layer, no I/O performed here).

    Returns:
        Topology: exchange, queues and bindings (pure data).
    """
    exchange = ExchangeDeclaration()

    main_queue = QueueDeclaration(
        name=MAIN_QUEUE,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": DLQ_QUEUE,
        },
    )
    dlq_queue = QueueDeclaration(name=DLQ_QUEUE)

    bindings: list[Binding] = [
        Binding(exchange=exchange.name, queue=MAIN_QUEUE, routing_key=routing_key)
        for routing_key in MESSAGE_ROUTING_KEYS
    ]
    bindings.append(
        Binding(exchange=exchange.name, queue=DLQ_QUEUE, routing_key=f"{DLQ_QUEUE}.#")
    )

    return Topology(
        exchange=exchange,
        queues=(main_queue, dlq_queue),
        bindings=tuple(bindings),
    )
