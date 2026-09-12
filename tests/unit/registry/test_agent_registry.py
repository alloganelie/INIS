"""Tests for AgentRegistry."""

import pytest

from app.registry.agent_registry import (
    AgentIdentity,
    AgentRegistry,
    AgentNotFoundError,
    AgentAlreadyRegisteredError,
    VALID_STATUSES,
)


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


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def test_register_and_get_agent(self) -> None:
        """Test registering and retrieving an agent."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)
        retrieved = registry.get("agent_1")

        assert retrieved.agent_id == "agent_1"
        assert retrieved.name == "Test Agent"
        assert retrieved.status == "available"

    def test_register_duplicate_raises_error(self) -> None:
        """Test that registering duplicate agent raises error."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)

        with pytest.raises(AgentAlreadyRegisteredError):
            registry.register("agent_1", identity)

    def test_get_nonexistent_raises_error(self) -> None:
        """Test that getting non-existent agent raises error."""
        registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError):
            registry.get("nonexistent")

    def test_unregister_agent(self) -> None:
        """Test unregistering an agent."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)
        registry.unregister("agent_1")

        with pytest.raises(AgentNotFoundError):
            registry.get("agent_1")

    def test_unregister_nonexistent_raises_error(self) -> None:
        """Test that unregistering non-existent agent raises error."""
        registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError):
            registry.unregister("nonexistent")

    def test_list_agents(self) -> None:
        """Test listing all agents."""
        registry = AgentRegistry()
        identity1 = create_test_identity("agent_1")
        identity2 = create_test_identity("agent_2")

        registry.register("agent_1", identity1)
        registry.register("agent_2", identity2)

        agents = registry.list_agents()

        assert len(agents) == 2
        agent_ids = {a.agent_id for a in agents}
        assert agent_ids == {"agent_1", "agent_2"}

    def test_update_status(self) -> None:
        """Test updating agent status."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)
        registry.update_status("agent_1", "degraded")

        agent = registry.get("agent_1")
        assert agent.status == "degraded"

    def test_update_status_invalid_raises_error(self) -> None:
        """Test that invalid status raises error."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)

        with pytest.raises(ValueError):
            registry.update_status("agent_1", "invalid_status")

    def test_update_heartbeat(self) -> None:
        """Test updating agent heartbeat."""
        from datetime import datetime, timedelta

        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)
        original_last_seen = identity.last_seen_at

        # Use a later time for the heartbeat
        later_time = datetime.utcnow() + timedelta(seconds=1)
        registry.update_heartbeat("agent_1", {"latency_ms_p95": 100}, now=later_time)

        agent = registry.get("agent_1")
        assert agent.last_seen_at != original_last_seen
        assert agent.health.get("latency_ms_p95") == 100

    def test_get_stale_agents(self) -> None:
        """Test getting stale agents."""
        from datetime import datetime, timedelta

        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)
        # Manually set last_seen_at to old time
        old_time = datetime.utcnow() - timedelta(seconds=120)
        identity.last_seen_at = old_time.isoformat(timespec="microseconds") + "Z"

        stale = registry.get_stale_agents(ttl_seconds=90)

        assert "agent_1" in stale

    def test_get_stale_agents_not_stale(self) -> None:
        """Test that recent agents are not stale."""
        registry = AgentRegistry()
        identity = create_test_identity("agent_1")

        registry.register("agent_1", identity)

        stale = registry.get_stale_agents(ttl_seconds=90)

        assert "agent_1" not in stale