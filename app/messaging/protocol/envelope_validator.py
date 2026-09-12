"""Envelope validator for INIS messaging protocol per §5.1 and §5.2."""

from app.core.errors import ValidationError


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


def validate(envelope: dict) -> None:
    """
    Validate an envelope against INIS protocol requirements.

    Raises:
        ValidationError: If the envelope is invalid per §5.1 and §5.2.
    """
    if not isinstance(envelope, dict):
        raise ValidationError("Envelope must be a dictionary")

    # protocol_version (required, must be "1.0")
    protocol_version = envelope.get("protocol_version")
    if protocol_version != "1.0":
        raise ValidationError(f"protocol_version must be '1.0', got: {protocol_version}")

    # message_id (required, must be MSG_ULID format)
    message_id = envelope.get("message_id")
    if not message_id or not isinstance(message_id, str):
        raise ValidationError("message_id is required and must be a string")
    if not message_id.startswith("MSG_"):
        raise ValidationError(f"message_id must start with 'MSG_', got: {message_id}")

    # correlation_id (required, must be CORR_ULID format)
    correlation_id = envelope.get("correlation_id")
    if not correlation_id or not isinstance(correlation_id, str):
        raise ValidationError("correlation_id is required and must be a string")
    if not correlation_id.startswith("CORR_"):
        raise ValidationError(f"correlation_id must start with 'CORR_', got: {correlation_id}")

    # timestamp (required, ISO 8601 UTC)
    timestamp = envelope.get("timestamp")
    if not timestamp or not isinstance(timestamp, str):
        raise ValidationError("timestamp is required and must be a string")
    # Basic ISO 8601 UTC check
    if not timestamp.endswith("Z"):
        raise ValidationError(f"timestamp must be ISO 8601 UTC ending with 'Z', got: {timestamp}")

    # sender (required object with agent_id, agent_version)
    sender = envelope.get("sender")
    if not isinstance(sender, dict):
        raise ValidationError("sender must be an object")
    if not sender.get("agent_id") or not isinstance(sender.get("agent_id"), str):
        raise ValidationError("sender.agent_id is required and must be a string")
    if not sender.get("agent_version") or not isinstance(sender.get("agent_version"), str):
        raise ValidationError("sender.agent_version is required and must be a string")
    # agent_instance_id is optional but if present must be string or null
    if "agent_instance_id" in sender and sender["agent_instance_id"] is not None:
        if not isinstance(sender["agent_instance_id"], str):
            raise ValidationError("sender.agent_instance_id must be a string or null")

    # recipient (required object with agent_id)
    recipient = envelope.get("recipient")
    if not isinstance(recipient, dict):
        raise ValidationError("recipient must be an object")
    if not recipient.get("agent_id") or not isinstance(recipient.get("agent_id"), str):
        raise ValidationError("recipient.agent_id is required and must be a string")
    # agent_instance_id is optional but if present must be string or null
    if "agent_instance_id" in recipient and recipient["agent_instance_id"] is not None:
        if not isinstance(recipient["agent_instance_id"], str):
            raise ValidationError("recipient.agent_instance_id must be a string or null")

    # message_type (required, must be in V1 list per §5.2)
    message_type = envelope.get("message_type")
    if not message_type or not isinstance(message_type, str):
        raise ValidationError("message_type is required and must be a string")
    if message_type not in VALID_MESSAGE_TYPES:
        raise ValidationError(f"Invalid message_type: {message_type}. Must be one of: {sorted(VALID_MESSAGE_TYPES)}")

    # priority (required, must be valid)
    priority = envelope.get("priority")
    if not priority or not isinstance(priority, str):
        raise ValidationError("priority is required and must be a string")
    if priority not in VALID_PRIORITIES:
        raise ValidationError(f"Invalid priority: {priority}. Must be one of: {sorted(VALID_PRIORITIES)}")

    # reply_to (optional, string or null)
    if "reply_to" in envelope and envelope["reply_to"] is not None:
        if not isinstance(envelope["reply_to"], str):
            raise ValidationError("reply_to must be a string or null")

    # ttl_seconds (required, positive integer)
    ttl_seconds = envelope.get("ttl_seconds")
    if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValidationError("ttl_seconds is required and must be a positive integer")

    # payload (required, object)
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    # security (required object)
    security = envelope.get("security")
    if not isinstance(security, dict):
        raise ValidationError("security must be an object")
    auth_method = security.get("auth_method")
    if not auth_method or auth_method not in VALID_AUTH_METHODS:
        raise ValidationError(f"security.auth_method must be one of: {sorted(VALID_AUTH_METHODS)}")
    if "token_id" in security and security["token_id"] is not None:
        if not isinstance(security["token_id"], str):
            raise ValidationError("security.token_id must be a string or null")
    scopes = security.get("scopes")
    if scopes is not None:
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            raise ValidationError("security.scopes must be a list of strings or null")

    # trace (required object)
    trace = envelope.get("trace")
    if not isinstance(trace, dict):
        raise ValidationError("trace must be an object")
    trace_id = trace.get("trace_id")
    if not trace_id or not isinstance(trace_id, str) or len(trace_id) != 32:
        raise ValidationError("trace.trace_id must be a 32-character hex string")
    span_id = trace.get("span_id")
    if not span_id or not isinstance(span_id, str) or len(span_id) != 16:
        raise ValidationError("trace.span_id must be a 16-character hex string")
    trace_corr_id = trace.get("correlation_id")
    if not trace_corr_id or trace_corr_id != correlation_id:
        raise ValidationError("trace.correlation_id must match envelope.correlation_id")
    trace_causation_id = trace.get("causation_id")
    if trace_causation_id is not None and trace_causation_id != envelope.get("causation_id"):
        raise ValidationError("trace.causation_id must match envelope.causation_id")