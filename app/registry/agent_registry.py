"""In-memory agent registry per §6."""

from datetime import datetime
from typing import Any

from app.core.errors import DomainError


class AgentNotFoundError(DomainError):
    """Raised when an agent is not found in the registry."""

    pass


class AgentAlreadyRegisteredError(DomainError):
    """Raised when attempting to register an agent that already exists."""

    pass


VALID_STATUSES = frozenset({"available", "degraded", "unavailable", "maintenance"})


class AgentIdentity:
    """Agent identity card per §6.2."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        version: str,
        status: str,
        capabilities: list[str],
        protocols: list[str],
        message_types: list[str],
        input_schemas: list[dict[str, Any]],
        output_schemas: list[dict[str, Any]],
        security_requirements: list[dict[str, Any]],
        health: dict[str, Any],
        performance_profile: dict[str, Any],
        learning_profile: dict[str, Any],
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")

        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.version = version
        self.status = status
        self.capabilities = capabilities
        self.protocols = protocols
        self.message_types = message_types
        self.input_schemas = input_schemas
        self.output_schemas = output_schemas
        self.security_requirements = security_requirements
        self.health = health
        self.performance_profile = performance_profile
        self.learning_profile = learning_profile
        self.registered_at = datetime.utcnow().isoformat(timespec="microseconds") + "Z"
        self.last_seen_at = self.registered_at

    def to_dict(self) -> dict[str, Any]:
        """Return identity as dictionary per §6.2."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "status": self.status,
            "capabilities": self.capabilities,
            "protocols": self.protocols,
            "message_types": self.message_types,
            "input_schemas": self.input_schemas,
            "output_schemas": self.output_schemas,
            "security_requirements": self.security_requirements,
            "health": self.health,
            "performance_profile": self.performance_profile,
            "learning_profile": self.learning_profile,
            "registered_at": self.registered_at,
            "last_seen_at": self.last_seen_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentIdentity":
        """Create AgentIdentity from dictionary."""
        identity = cls(
            agent_id=data["agent_id"],
            name=data["name"],
            description=data["description"],
            version=data["version"],
            status=data["status"],
            capabilities=data.get("capabilities", []),
            protocols=data.get("protocols", []),
            message_types=data.get("message_types", []),
            input_schemas=data.get("input_schemas", []),
            output_schemas=data.get("output_schemas", []),
            security_requirements=data.get("security_requirements", []),
            health=data.get("health", {}),
            performance_profile=data.get("performance_profile", {}),
            learning_profile=data.get("learning_profile", {}),
        )
        identity.registered_at = data.get("registered_at", identity.registered_at)
        identity.last_seen_at = data.get("last_seen_at", identity.last_seen_at)
        return identity


class AgentRegistry:
    """In-memory agent registry per §6."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentIdentity] = {}

    def register(self, agent_id: str, identity: AgentIdentity) -> None:
        """Register a new agent."""
        if agent_id in self._agents:
            raise AgentAlreadyRegisteredError(f"Agent {agent_id} already registered")
        if agent_id != identity.agent_id:
            raise ValueError("agent_id must match identity.agent_id")
        self._agents[agent_id] = identity

    def get(self, agent_id: str) -> AgentIdentity:
        """Get agent identity by ID."""
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        return self._agents[agent_id]

    def list_agents(self) -> list[AgentIdentity]:
        """List all registered agents."""
        return list(self._agents.values())

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        del self._agents[agent_id]

    def update_status(self, agent_id: str, status: str) -> None:
        """Update agent status."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
        agent = self.get(agent_id)
        agent.status = status
        agent.last_seen_at = datetime.utcnow().isoformat(timespec="microseconds") + "Z"

    def update_heartbeat(
        self, agent_id: str, health: dict[str, Any] | None = None, now: datetime | None = None
    ) -> None:
        """Update agent last_seen_at and optionally health info."""
        agent = self.get(agent_id)
        if now is None:
            now = datetime.utcnow()
        agent.last_seen_at = now.isoformat(timespec="microseconds") + "Z"
        if health is not None:
            agent.health.update(health)

    def get_stale_agents(self, ttl_seconds: int = 90, now: datetime | None = None) -> list[str]:
        """Return list of agent_ids that have not sent heartbeat within TTL."""
        if now is None:
            now = datetime.utcnow().replace(tzinfo=None)
        else:
            now = now.replace(tzinfo=None)
        stale = []
        for agent_id, agent in self._agents.items():
            last_seen_str = agent.last_seen_at.replace("Z", "+00:00")
            last_seen = datetime.fromisoformat(last_seen_str).replace(tzinfo=None)
            if (now - last_seen).total_seconds() > ttl_seconds:
                stale.append(agent_id)
        return stale