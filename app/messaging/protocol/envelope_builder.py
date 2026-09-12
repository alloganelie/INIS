"""Envelope builder for INIS messaging protocol per §5.1."""

from datetime import datetime
from typing import Any
from typing import Optional

from app.domain.value_objects.ulid import ULID


VALID_MESSAGE_TYPES = frozenset(
    {
        "AGENT_REGISTER",
        "AGENT_UPDATE",
        "AGENT_HEARTBEAT",
        "CAPABILITY_QUERY",
        "INFORMATION_REQUEST",
        "INFORMATION_RESPONSE",
        "SOURCE_REQUEST",
        "EVIDENCE_REQUEST",
        "DATA_REQUEST",
        "RESEARCH_REQUEST",
        "RESEARCH_PROGRESS",
        "RESEARCH_COMPLETED",
        "AGENT_DELEGATION_REQUEST",
        "AGENT_DELEGATION_RESPONSE",
        "CLARIFICATION_REQUEST",
        "CONFLICT_REPORT",
        "LOW_CONFIDENCE_REPORT",
        "ACCESS_DENIED",
        "VALIDATION_ERROR",
        "EXECUTION_ERROR",
        "CANCEL_REQUEST",
        "CANCELLED",
        "AUDIT_EVENT",
    }
)

VALID_PRIORITIES = frozenset({"low", "normal", "high", "critical"})

VALID_AUTH_METHODS = frozenset({"mtls", "jwt", "api_key"})


class EnvelopeBuilder:
    """Builds INIS protocol envelopes conforming to §5.1."""

    PROTOCOL_VERSION = "1.0"

    def __init__(
        self,
        default_sender_agent_id: str,
        default_sender_agent_version: str,
        default_sender_agent_instance_id: Optional[str] = None,
    ) -> None:
        self._default_sender_agent_id = default_sender_agent_id
        self._default_sender_agent_version = default_sender_agent_version
        self._default_sender_agent_instance_id = default_sender_agent_instance_id

    def build(
        self,
        message_type: str,
        recipient_agent_id: str,
        payload: dict[str, Any],
        *,
        sender_agent_id: Optional[str] = None,
        sender_agent_version: Optional[str] = None,
        sender_agent_instance_id: Optional[str] = None,
        recipient_agent_instance_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        priority: str = "normal",
        reply_to: Optional[str] = None,
        ttl_seconds: int = 300,
        security_auth_method: str = "mtls",
        security_token_id: Optional[str] = None,
        security_scopes: Optional[list[str]] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a complete envelope dict per §5.1 specification."""
        if message_type not in VALID_MESSAGE_TYPES:
            raise ValueError(f"Invalid message_type: {message_type}")

        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")

        if security_auth_method not in VALID_AUTH_METHODS:
            raise ValueError(f"Invalid auth_method: {security_auth_method}")

        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        message_id = ULID.new("MSG_")
        corr_id = correlation_id or ULID.new("CORR_")

        now_utc = datetime.utcnow().isoformat(timespec="microseconds") + "Z"

        sender_id = sender_agent_id or self._default_sender_agent_id
        sender_version = sender_agent_version or self._default_sender_agent_version
        sender_instance_id = sender_agent_instance_id or self._default_sender_agent_instance_id

        if trace_id is None:
            import secrets
            trace_id = secrets.token_hex(16)
        if span_id is None:
            import secrets
            span_id = secrets.token_hex(8)

        envelope: dict[str, Any] = {
            "protocol_version": self.PROTOCOL_VERSION,
            "message_id": message_id,
            "correlation_id": corr_id,
            "causation_id": causation_id,
            "timestamp": now_utc,
            "sender": {
                "agent_id": sender_id,
                "agent_instance_id": sender_instance_id,
                "agent_version": sender_version,
            },
            "recipient": {
                "agent_id": recipient_agent_id,
                "agent_instance_id": recipient_agent_instance_id,
            },
            "message_type": message_type,
            "priority": priority,
            "reply_to": reply_to,
            "ttl_seconds": ttl_seconds,
            "payload": payload,
            "security": {
                "auth_method": security_auth_method,
                "token_id": security_token_id,
                "scopes": security_scopes or [],
            },
            "trace": {
                "trace_id": trace_id,
                "span_id": span_id,
                "correlation_id": corr_id,
                "causation_id": causation_id,
            },
        }

        return envelope