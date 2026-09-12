"""Heartbeat worker logic per §6.3."""

from datetime import datetime
from typing import Any

from app.registry.agent_registry import AgentRegistry


DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
DEFAULT_TTL_SECONDS = 90


class HeartbeatWorker:
    """
    Pure logic heartbeat worker per §6.3.

    This class contains no asyncio loop - it provides pure logic methods
    that can be called by an external scheduler.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._registry = registry
        self._ttl_seconds = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def check_stale(self, now: datetime | None = None) -> list[str]:
        """
        Check for stale agents that haven't sent heartbeat within TTL.

        Args:
            now: Current time (for testing). Defaults to datetime.utcnow().

        Returns:
            List of agent_ids that are stale.
        """
        if now is None:
            now = datetime.utcnow()

        stale_agent_ids = self._registry.get_stale_agents(self._ttl_seconds, now)
        return stale_agent_ids

    def mark_stale_as_unavailable(self, now: datetime | None = None) -> list[str]:
        """
        Mark stale agents as unavailable.

        Args:
            now: Current time (for testing). Defaults to datetime.utcnow().

        Returns:
            List of agent_ids that were marked unavailable.
        """
        stale_agent_ids = self.check_stale(now)
        for agent_id in stale_agent_ids:
            self._registry.update_status(agent_id, "unavailable")
        return stale_agent_ids

    def process_heartbeat(
        self,
        agent_id: str,
        health: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> bool:
        """
        Process a heartbeat from an agent.

        Args:
            agent_id: ID of the agent sending heartbeat.
            health: Optional health information.
            now: Current time (for testing).

        Returns:
            True if heartbeat was processed, False if agent not found.
        """
        try:
            self._registry.update_heartbeat(agent_id, health, now)
            return True
        except Exception:
            return False

    def get_next_check_time(self, last_check: datetime | None = None) -> datetime:
        """
        Get the next time the worker should check for stale agents.

        Args:
            last_check: Last check time. Defaults to now.

        Returns:
            Next check time.
        """
        if last_check is None:
            last_check = datetime.utcnow()
        from datetime import timedelta
        return last_check + timedelta(seconds=self._ttl_seconds // 3)