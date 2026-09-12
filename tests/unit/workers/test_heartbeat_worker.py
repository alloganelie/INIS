"""Tests for HeartbeatWorker."""

from datetime import datetime, timedelta

import pytest

from app.registry.agent_registry import AgentIdentity, AgentRegistry
from app.workers.heartbeat_worker import HeartbeatWorker, DEFAULT_TTL_SECONDS


def create_test_identity(agent_id: str = "test_agent") -> AgentIdentity:
    """Create a test agent identity."""
    return AgentIdentity(
        agent_id=agent_id,
        name="Test Agent",
        description="A test agent",
        version="1.0.0",
        status="available",
        capabilities=["test_capability"],
        protocols=["amqp"],
        message_types=["INFORMATION_REQUEST"],
        input_schemas=[],
        output_schemas=[],
        security_requirements=[],
        health={},
        performance_profile={},
        learning_profile={},
    )


class TestHeartbeatWorker:
    """Tests for HeartbeatWorker class."""

    def test_check_stale_returns_stale_agents(self) -> None:
        """Test check_stale returns agents that haven't sent heartbeat within TTL."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")
        registry.register("agent_1", identity)

        # Set last_seen_at to 120 seconds ago (TTL is 90)
        old_time = datetime.utcnow() - timedelta(seconds=120)
        identity.last_seen_at = old_time.isoformat(timespec="microseconds") + "Z"

        worker = HeartbeatWorker(registry, ttl_seconds=90)
        stale = worker.check_stale()

        assert "agent_1" in stale

    def test_check_stale_returns_empty_for_recent_agents(self) -> None:
        """Test check_stale returns empty for agents with recent heartbeat."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")
        registry.register("agent_1", identity)

        worker = HeartbeatWorker(registry, ttl_seconds=90)
        stale = worker.check_stale()

        assert "agent_1" not in stale
        assert stale == []

    def test_check_stale_uses_provided_time(self) -> None:
        """Test check_stale uses provided 'now' time for testing."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")
        registry.register("agent_1", identity)

        # Set last_seen_at to 120 seconds ago
        old_time = datetime.utcnow() - timedelta(seconds=120)
        identity.last_seen_at = old_time.isoformat(timespec="microseconds") + "Z"

        # Use a 'now' that's only 30 seconds after last_seen
        check_time = old_time + timedelta(seconds=30)
        worker = HeartbeatWorker(registry, ttl_seconds=90)
        stale = worker.check_stale(now=check_time)

        # Agent should NOT be stale with this check_time
        assert "agent_1" not in stale

    def test_mark_stale_as_unavailable(self) -> None:
        """Test mark_stale_as_unavailable updates agent status."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")
        registry.register("agent_1", identity)

        # Set last_seen_at to 120 seconds ago
        old_time = datetime.utcnow() - timedelta(seconds=120)
        identity.last_seen_at = old_time.isoformat(timespec="microseconds") + "Z"

        worker = HeartbeatWorker(registry, ttl_seconds=90)
        marked = worker.mark_stale_as_unavailable()

        assert "agent_1" in marked
        agent = registry.get("agent_1")
        assert agent.status == "unavailable"

    def test_process_heartbeat_updates_last_seen(self) -> None:
        """Test process_heartbeat updates last_seen_at."""
        from datetime import datetime, timedelta

        registry = AgentRegistry()
        identity = create_test_identity("agent_1")
        registry.register("agent_1", identity)

        original_last_seen = identity.last_seen_at

        # Use a later time for the heartbeat
        later_time = datetime.utcnow() + timedelta(seconds=1)
        worker = HeartbeatWorker(registry, ttl_seconds=90)
        result = worker.process_heartbeat("agent_1", health={"latency_ms_p95": 50}, now=later_time)

        assert result is True
        agent = registry.get("agent_1")
        assert agent.last_seen_at != original_last_seen
        assert agent.health.get("latency_ms_p95") == 50

    def test_process_heartbeat_returns_false_for_unknown_agent(self) -> None:
        """Test process_heartbeat returns False for unknown agent."""
        registry = AgentRegistry()
        worker = HeartbeatWorker(registry, ttl_seconds=90)

        result = worker.process_heartbeat("unknown_agent")

        assert result is False

    def test_get_next_check_time(self) -> None:
        """Test get_next_check_time returns correct next check time."""
        registry = AgentRegistry()
        worker = HeartbeatWorker(registry, ttl_seconds=90)

        now = datetime.utcnow()
        next_check = worker.get_next_check_time(now)

        # Default TTL is 90, check interval should be TTL/3 = 30
        expected = now + timedelta(seconds=30)
        # Allow small delta for execution time
        assert abs((next_check - expected).total_seconds()) < 1