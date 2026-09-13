"""Tests for AMQP topology declarations per §5.2 (pure logic, no I/O)."""

from app.messaging.amqp.topology import DLQ_QUEUE
from app.messaging.amqp.topology import MAIN_QUEUE
from app.messaging.amqp.topology import declare_topology
from app.messaging.protocol.envelope_builder import VALID_MESSAGE_TYPES


class TestAmqpTopology:
    """4 tests covering queues, routing keys and purity."""

    def test_main_queue_name(self) -> None:
        """Main queue must be inis.messages."""
        topology = declare_topology()
        queue_names = [q.name for q in topology.queues]
        assert MAIN_QUEUE == "inis.messages"
        assert MAIN_QUEUE in queue_names

    def test_dlq_queue_name(self) -> None:
        """Dead-letter queue must be inis.messages.dlq."""
        topology = declare_topology()
        queue_names = [q.name for q in topology.queues]
        assert DLQ_QUEUE == "inis.messages.dlq"
        assert DLQ_QUEUE in queue_names

    def test_routing_keys_match_v1_message_types(self) -> None:
        """One binding per V1 message type on the main queue."""
        topology = declare_topology()
        main_keys = {
            b.routing_key for b in topology.bindings if b.queue == MAIN_QUEUE
        }
        assert main_keys == set(VALID_MESSAGE_TYPES)

    def test_declare_topology_is_pure_and_deterministic(self) -> None:
        """No I/O: repeated calls return equal, JSON-serialisable data."""
        first = declare_topology()
        second = declare_topology()
        assert first == second
        assert first.to_dict() == second.to_dict()
