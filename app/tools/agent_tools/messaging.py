"""``send_agent_request`` and ``receive_agent_result`` internal tools per §21.

Transport contract: the tools never fabricate an answer. A request is handed
to an *agent channel*; a result only exists once a responder deposited it. A
missing result therefore surfaces as ``InfrastructureError`` instead of an
empty envelope, so the planner can degrade explicitly (§0.2).

The default channel is in-process: correlation ids are shared between
``send_agent_request`` and ``receive_agent_result`` inside one runtime. When a
broker is configured, the caller passes a channel backed by it (§4.4).
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from app.core.errors import InfrastructureError, ValidationError
from app.messaging.protocol.envelope_validator import validate as validate_envelope

__all__ = ["AgentChannel", "InProcessAgentChannel", "default_channel", "receive_agent_result", "send_agent_request"]


class AgentChannel(Protocol):
    """Minimal transport façade used by the §21 agent messaging tools."""

    async def deliver(self, agent_id: str, envelope: dict[str, Any]) -> None:
        """Hand *envelope* to *agent*."""

    async def fetch(self, correlation_id: str) -> dict[str, Any] | None:
        """Return the result envelope for *correlation_id*, if available."""


class InProcessAgentChannel:
    """In-process channel keeping pending requests and completed results.

    Results are never synthesised: a responder (test double, worker, broker
    consumer) must call :meth:`deposit` before the result can be received.
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}

    async def deliver(self, agent_id: str, envelope: dict[str, Any]) -> None:
        self._pending[envelope["correlation_id"]] = {
            "agent_id": agent_id,
            "envelope": dict(envelope),
        }

    async def fetch(self, correlation_id: str) -> dict[str, Any] | None:
        return self._results.pop(correlation_id, None)

    def deposit(self, correlation_id: str, envelope: Mapping[str, Any]) -> None:
        """Store a completed result so ``receive_agent_result`` can return it."""
        self._results[correlation_id] = dict(envelope)

    def take_pending(self, correlation_id: str) -> dict[str, Any] | None:
        """Remove and return the pending request for *correlation_id*."""
        return self._pending.pop(correlation_id, None)


_CHANNEL: InProcessAgentChannel | None = None


def default_channel() -> InProcessAgentChannel:
    """Return the process-wide in-process agent channel."""
    global _CHANNEL
    if _CHANNEL is None:
        _CHANNEL = InProcessAgentChannel()
    return _CHANNEL


async def send_agent_request(
    agent_id: str,
    request: Mapping[str, Any],
    *,
    channel: AgentChannel | None = None,
) -> dict[str, Any]:
    """Validate and deliver *request* to *agent_id* (§21).

    Args:
        agent_id: Target agent (§5.2 routing).
        request: Envelope to send; validated against §5.1 first.
        channel: Transport; defaults to the in-process channel.

    Returns:
        The validated envelope actually delivered.

    Raises:
        ValidationError: If the target or the envelope is invalid (§5.1).
        InfrastructureError: If the transport rejects delivery.
    """
    if not agent_id or not str(agent_id).strip():
        raise ValidationError("agent_id is required to send an agent request (§5)")
    if not isinstance(request, Mapping):
        raise ValidationError("request must be an envelope mapping (§5.1)")
    envelope = dict(request)
    validate_envelope(envelope)
    if not envelope.get("correlation_id"):
        raise ValidationError("envelope must carry a correlation_id (§5.1)")
    active_channel = channel if channel is not None else default_channel()
    try:
        await active_channel.deliver(agent_id, envelope)
    except InfrastructureError:
        raise
    except Exception as exc:  # transport failure must not look like success
        raise InfrastructureError(
            f"failed to deliver envelope to {agent_id}: {exc}"
        ) from exc
    return envelope


async def receive_agent_result(
    correlation_id: str,
    *,
    channel: AgentChannel | None = None,
) -> dict[str, Any]:
    """Return the completed result envelope for *correlation_id* (§21).

    Args:
        correlation_id: Correlation of the awaited request.
        channel: Transport; defaults to the in-process channel.

    Returns:
        The deposited result envelope.

    Raises:
        ValidationError: If *correlation_id* is empty.
        InfrastructureError: If no result exists yet — absence is reported,
            never replaced by an empty envelope (§0.2).
    """
    if not correlation_id or not str(correlation_id).strip():
        raise ValidationError("correlation_id is required to receive a result (§5.3)")
    active_channel = channel if channel is not None else default_channel()
    result = await active_channel.fetch(correlation_id)
    if result is None:
        raise InfrastructureError(
            f"no result available for correlation_id {correlation_id} (§5.3)"
        )
    return result
