"""Message handlers for V1 envelope types (§5.2)."""

from app.messaging.handlers.agent_register_handler import SUPPORTED_VERSIONS_KEY
from app.messaging.handlers.agent_register_handler import AgentRegisterHandler

__all__ = ["AgentRegisterHandler", "SUPPORTED_VERSIONS_KEY"]