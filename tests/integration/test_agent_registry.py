"""§6/§41.11 — agent registry integration: discovery, heartbeat and versioning.

The registry is what lets INIS route a task to a capable agent (§6, §41.10) and
notice when that agent stops answering. These tests exercise the pieces together:
identity cards, the capability index used for discovery, heartbeat/staleness,
and the ``AGENT_REGISTER`` version negotiation (§41.11) that decides which
protocol the two sides speak.

No Docker, no broker: the registry and the handlers are in-process components.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ValidationError
from app.messaging.handlers.agent_register_handler import AgentRegisterHandler
from app.messaging.protocol.versioning import PROTOCOL_COMPATIBILITY
from app.registry.agent_registry import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    AgentRegistry,
)
from app.registry.capability_index import CapabilityIndex
from tests.factories import make_agent_identity

AGENT_ONE = "AGENT_SEARCH"
AGENT_TWO = "AGENT_FILES"


@pytest.fixture
def registry() -> AgentRegistry:
    """Return an empty registry."""
    return AgentRegistry()


@pytest.fixture
def index() -> CapabilityIndex:
    """Return an empty capability index."""
    return CapabilityIndex()


def _register(
    registry: AgentRegistry, index: CapabilityIndex, agent_id: str, **caps: object
) -> None:
    """Register an agent in both the registry and the capability index."""
    identity = make_agent_identity(agent_id, **caps)
    registry.register(agent_id, identity)
    index.add_agent(agent_id, list(identity.capabilities))


class TestRegistrationAndDiscovery:
    """§6 — an agent is discoverable by the capability it advertises."""

    def test_registered_agent_is_discoverable_by_capability(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """A registered capability maps back to its agent."""
        _register(registry, index, AGENT_ONE, capabilities=["web_search"])

        assert registry.get(AGENT_ONE).capabilities == ["web_search"]
        assert index.get_agents_for_capability("web_search") == [AGENT_ONE]
        assert index.has_capability("web_search") is True

    def test_duplicate_registration_is_refused(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """Registering the same id twice is an error, not a silent overwrite."""
        _register(registry, index, AGENT_ONE)

        with pytest.raises(AgentAlreadyRegisteredError):
            registry.register(AGENT_ONE, make_agent_identity(AGENT_ONE))

    def test_unknown_agent_is_reported(self, registry: AgentRegistry) -> None:
        """Reading an unknown agent never returns a fabricated identity."""
        with pytest.raises(AgentNotFoundError):
            registry.get("AGENT_MISSING")

    def test_unregister_removes_the_agent_from_discovery(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """A departed agent stops being routed to (§41.10)."""
        _register(registry, index, AGENT_ONE, capabilities=["web_search"])
        index.remove_agent(AGENT_ONE)
        registry.unregister(AGENT_ONE)

        assert registry.list_agents() == []
        assert index.get_agents_for_capability("web_search") == []

    def test_capability_update_moves_the_agent(self, index: CapabilityIndex) -> None:
        """A capability change is reflected instead of accumulating stale entries."""
        index.add_agent(AGENT_ONE, ["web_search"])
        index.update_agent(AGENT_ONE, ["file_read"])

        assert index.get_agents_for_capability("web_search") == []
        assert index.get_agents_for_capability("file_read") == [AGENT_ONE]

    def test_index_round_trips_through_its_projection(self, index: CapabilityIndex) -> None:
        """The exported index rebuilds an equivalent index (§6 discovery)."""
        index.add_agent(AGENT_ONE, ["web_search"])
        index.add_agent(AGENT_TWO, ["web_search", "file_read"])

        rebuilt = CapabilityIndex.from_dict(index.to_dict())

        assert sorted(rebuilt.get_agents_for_capability("web_search")) == sorted(
            [AGENT_ONE, AGENT_TWO]
        )
        # The order is stable and survives the round-trip (§5.3 idempotence):
        # an unsorted projection would vary with the hash seed of the process.
        assert index.get_capabilities_for_agent(AGENT_TWO) == ["file_read", "web_search"]
        assert rebuilt.get_capabilities_for_agent(AGENT_TWO) == ["file_read", "web_search"]
        assert rebuilt.to_dict() == index.to_dict()

    def test_projection_ignores_insertion_order(self) -> None:
        """Two indexes built in a different order project identically (§5.3)."""
        first = CapabilityIndex()
        first.add_agent(AGENT_ONE, ["file_read", "web_search"])
        first.add_agent(AGENT_TWO, ["web_search"])

        second = CapabilityIndex()
        second.add_agent(AGENT_TWO, ["web_search"])
        second.add_agent(AGENT_ONE, ["web_search", "file_read"])

        assert first.to_dict() == second.to_dict()
        assert first.list_capabilities() == second.list_capabilities() == [
            "file_read",
            "web_search",
        ]


class TestHeartbeatAndStaleness:
    """§6.3 — a silent agent must be detected, not assumed healthy."""

    def test_heartbeat_refreshes_last_seen(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """A heartbeat carries the agent out of the stale set."""
        _register(registry, index, AGENT_ONE)
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

        registry.update_heartbeat(AGENT_ONE, {"healthy": True}, now=now)

        identity = registry.get(AGENT_ONE)
        assert identity.last_seen_at.startswith("2026-09-28T12:00:00")
        assert identity.health["healthy"] is True
        assert registry.get_stale_agents(ttl_seconds=90, now=now) == []

    def test_silent_agent_becomes_stale(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """No heartbeat within the TTL means the agent is no longer usable."""
        _register(registry, index, AGENT_ONE)
        registered_at = datetime.fromisoformat(
            registry.get(AGENT_ONE).last_seen_at.replace("Z", "+00:00")
        )
        later = registered_at + timedelta(seconds=120)

        assert registry.get_stale_agents(ttl_seconds=90, now=later) == [AGENT_ONE]

    def test_status_update_is_validated(
        self, registry: AgentRegistry, index: CapabilityIndex
    ) -> None:
        """§6.2 — only the four documented statuses exist."""
        _register(registry, index, AGENT_ONE)

        registry.update_status(AGENT_ONE, "degraded")
        assert registry.get(AGENT_ONE).status == "degraded"

        with pytest.raises(ValueError):
            registry.update_status(AGENT_ONE, "sleeping")


class TestProtocolNegotiation:
    """§41.11 — AGENT_REGISTER agrees on a version the two sides share."""

    def _envelope(self, agent_id: str, declared: list[str] | None) -> dict:
        """Build an AGENT_REGISTER envelope declaring *declared*."""
        payload: dict[str, object] = {}
        if declared is not None:
            payload["supported_protocol_versions"] = declared
        return {
            "protocol_version": PROTOCOL_COMPATIBILITY.preferred_version,
            "sender": {"agent_id": agent_id},
            "payload": payload,
        }

    def test_preferred_version_wins_when_both_sides_support_it(self) -> None:
        """Negotiation is deterministic: our preferred version is chosen."""
        handler = AgentRegisterHandler()

        chosen = handler.negotiate(
            self._envelope(AGENT_ONE, list(PROTOCOL_COMPATIBILITY.supported_versions))
        )

        assert chosen == PROTOCOL_COMPATIBILITY.preferred_version
        assert handler.negotiated(AGENT_ONE) == chosen

    def test_silent_agent_is_tolerated_at_the_envelope_version(self) -> None:
        """An agent declaring nothing speaks the version of its envelope."""
        handler = AgentRegisterHandler()

        chosen = handler.negotiate(self._envelope(AGENT_TWO, None))

        assert chosen == PROTOCOL_COMPATIBILITY.preferred_version
        assert handler.negotiated_versions == {AGENT_TWO: chosen}

    def test_unknown_major_is_refused_with_the_supported_versions(self) -> None:
        """§41.11 — an incompatible agent is rejected, and told what to speak."""
        handler = AgentRegisterHandler()

        with pytest.raises(ValidationError, match="version_supported"):
            handler.negotiate(self._envelope(AGENT_ONE, ["2.0"]))

        assert handler.negotiated(AGENT_ONE) is None

    async def test_handler_call_dispatches_like_a_message_handler(self) -> None:
        """The handler honours the §5.2 async ``MessageHandler`` signature."""
        handler = AgentRegisterHandler()

        chosen = await handler(self._envelope(AGENT_ONE, ["1.0"]))

        assert chosen == "1.0"

