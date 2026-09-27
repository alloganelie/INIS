"""Agent cooperation tools per §21: discovery (§6) and envelopes (§5)."""

from app.tools.agent_tools.discovery import (
    discover_agents,
    query_agent_capabilities,
)
from app.tools.agent_tools.messaging import (
    AgentChannel,
    InProcessAgentChannel,
    default_channel,
    receive_agent_result,
    send_agent_request,
)

__all__ = [
    "AgentChannel",
    "InProcessAgentChannel",
    "default_channel",
    "discover_agents",
    "query_agent_capabilities",
    "receive_agent_result",
    "send_agent_request",
]
