"""AGENT_REGISTER version negotiation handler (§41.11).

The registering agent declares its supported versions in the payload under
``supported_protocol_versions``; agents that declare nothing (older
agents) are assumed to speak the version of their envelope — backward
tolerance. A registration without any common version is rejected with
VALIDATION_ERROR semantics: a ``ValidationError`` whose message carries
``version_supported``.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ValidationError
from app.messaging.protocol.versioning import PROTOCOL_COMPATIBILITY
from app.messaging.protocol.versioning import ProtocolCompatibility

Envelope = dict[str, Any]
#: Payload key used by agents to declare their versions at registration.
SUPPORTED_VERSIONS_KEY = "supported_protocol_versions"


class AgentRegisterHandler:
    """Negotiate and record the protocol version of a registering agent."""

    def __init__(
        self, compatibility: ProtocolCompatibility | None = None
    ) -> None:
        self._compatibility = compatibility or PROTOCOL_COMPATIBILITY
        self._negotiated: dict[str, str] = {}

    @property
    def compatibility(self) -> ProtocolCompatibility:
        """The compatibility policy used for negotiation."""
        return self._compatibility

    @property
    def negotiated_versions(self) -> dict[str, str]:
        """Copy of ``{agent_id: negotiated version}`` for registered agents."""
        return dict(self._negotiated)

    def negotiated(self, agent_id: str) -> str | None:
        """Return the version agreed with *agent_id*, if registered."""
        return self._negotiated.get(agent_id)

    def negotiate(self, envelope: Envelope) -> str:
        """Run the §41.11 negotiation on an AGENT_REGISTER envelope.

        Returns:
            The agreed version (our ``preferred_version`` whenever both
            sides support it, else the newest common one).

        Raises:
            ValueError: malformed envelope, payload or declaration list.
            ValidationError: no common version — the message carries
                ``version_supported`` so the caller can answer
                VALIDATION_ERROR (§41.11).
        """
        if not isinstance(envelope, dict):
            raise ValueError("envelope must be a dict")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        declared = payload.get(SUPPORTED_VERSIONS_KEY)
        if declared is None:
            # Backward tolerance: assume the envelope's own version.
            declared = [envelope.get("protocol_version") or self._compatibility.preferred_version]
        if isinstance(declared, str) or not isinstance(declared, list):
            raise ValueError(
                f"{SUPPORTED_VERSIONS_KEY} must be a list of version strings"
            )

        chosen = self._compatibility.negotiate(declared)
        if chosen is None:
            raise ValidationError(
                "no common protocol version for AGENT_REGISTER: agent declares "
                f"{list(declared)}, "
                f"version_supported={list(self._compatibility.supported_versions)} (§41.11)"
            )

        sender = envelope.get("sender")
        agent_id = sender.get("agent_id") if isinstance(sender, dict) else None
        if agent_id:
            self._negotiated[agent_id] = chosen
        return chosen

    async def __call__(self, envelope: Envelope) -> str:
        """MessageHandler entry point (§5.2 dispatch signature)."""
        return self.negotiate(envelope)
