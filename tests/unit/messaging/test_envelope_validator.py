"""Tests for envelope validator per §5.1 and §5.2."""

import pytest

from app.messaging.protocol.envelope_builder import EnvelopeBuilder
from app.messaging.protocol.envelope_validator import validate
from app.core.errors import ValidationError


class TestEnvelopeValidator:
    """Tests for validate() function."""

    def test_validate_ok(self) -> None:
        """Test that a valid envelope passes validation."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        # Should not raise
        validate(envelope)

    def test_validate_rejects_bad_message_type(self) -> None:
        """Test that invalid message_type is rejected per §5.2."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        # Tamper with message_type
        envelope["message_type"] = "INVALID_TYPE"

        with pytest.raises(ValidationError, match="Invalid message_type"):
            validate(envelope)

    def test_validate_rejects_wrong_protocol_version(self) -> None:
        """Test that wrong protocol_version is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["protocol_version"] = "2.0"

        with pytest.raises(ValidationError, match="protocol_version must be '1.0'"):
            validate(envelope)

    def test_validate_rejects_missing_message_id(self) -> None:
        """Test that missing message_id is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        del envelope["message_id"]

        with pytest.raises(ValidationError, match="message_id is required"):
            validate(envelope)

    def test_validate_rejects_invalid_message_id_prefix(self) -> None:
        """Test that message_id without MSG_ prefix is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["message_id"] = "INV_01ABCDEFGHIJKLMNOPQRSTUV"

        with pytest.raises(ValidationError, match="message_id must start with 'MSG_'"):
            validate(envelope)

    def test_validate_rejects_missing_correlation_id(self) -> None:
        """Test that missing correlation_id is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        del envelope["correlation_id"]

        with pytest.raises(ValidationError, match="correlation_id is required"):
            validate(envelope)

    def test_validate_rejects_invalid_correlation_id_prefix(self) -> None:
        """Test that correlation_id without CORR_ prefix is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["correlation_id"] = "INV_01ABCDEFGHIJKLMNOPQRSTUV"

        with pytest.raises(ValidationError, match="correlation_id must start with 'CORR_'"):
            validate(envelope)

    def test_validate_rejects_missing_timestamp(self) -> None:
        """Test that missing timestamp is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        del envelope["timestamp"]

        with pytest.raises(ValidationError, match="timestamp is required"):
            validate(envelope)

    def test_validate_rejects_non_utc_timestamp(self) -> None:
        """Test that non-UTC timestamp is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["timestamp"] = "2024-01-01T00:00:00+01:00"

        with pytest.raises(ValidationError, match="timestamp must be ISO 8601 UTC ending with 'Z'"):
            validate(envelope)

    def test_validate_rejects_missing_sender(self) -> None:
        """Test that missing sender is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        del envelope["sender"]

        with pytest.raises(ValidationError, match="sender must be an object"):
            validate(envelope)

    def test_validate_rejects_sender_missing_agent_id(self) -> None:
        """Test that sender without agent_id is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["sender"] = {"agent_version": "1.0.0"}

        with pytest.raises(ValidationError, match="sender.agent_id is required"):
            validate(envelope)

    def test_validate_rejects_sender_missing_agent_version(self) -> None:
        """Test that sender without agent_version is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["sender"] = {"agent_id": "agent-123"}

        with pytest.raises(ValidationError, match="sender.agent_version is required"):
            validate(envelope)

    def test_validate_rejects_missing_recipient(self) -> None:
        """Test that missing recipient is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        del envelope["recipient"]

        with pytest.raises(ValidationError, match="recipient must be an object"):
            validate(envelope)

    def test_validate_rejects_recipient_missing_agent_id(self) -> None:
        """Test that recipient without agent_id is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["recipient"] = {}

        with pytest.raises(ValidationError, match="recipient.agent_id is required"):
            validate(envelope)

    def test_validate_rejects_invalid_priority(self) -> None:
        """Test that invalid priority is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["priority"] = "urgent"

        with pytest.raises(ValidationError, match="Invalid priority"):
            validate(envelope)

    def test_validate_rejects_invalid_ttl(self) -> None:
        """Test that non-positive ttl_seconds is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["ttl_seconds"] = 0

        with pytest.raises(ValidationError, match="ttl_seconds is required and must be a positive integer"):
            validate(envelope)

    def test_validate_rejects_invalid_payload(self) -> None:
        """Test that non-object payload is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["payload"] = "not an object"

        with pytest.raises(ValidationError, match="payload must be an object"):
            validate(envelope)

    def test_validate_rejects_invalid_security(self) -> None:
        """Test that invalid security object is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["security"] = {"auth_method": "oauth"}

        with pytest.raises(ValidationError, match="security.auth_method must be one of"):
            validate(envelope)

    def test_validate_rejects_invalid_trace(self) -> None:
        """Test that invalid trace object is rejected."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["trace"] = {"trace_id": "short", "span_id": "short"}

        with pytest.raises(ValidationError, match="trace.trace_id must be a 32-character hex string"):
            validate(envelope)

    def test_validate_trace_correlation_mismatch(self) -> None:
        """Test that trace.correlation_id must match envelope.correlation_id."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
        )

        envelope["trace"]["correlation_id"] = "CORR_DIFFERENT01ABCDEFGHIJKLMNOP"

        with pytest.raises(ValidationError, match="trace.correlation_id must match envelope.correlation_id"):
            validate(envelope)

    def test_validate_trace_causation_mismatch(self) -> None:
        """Test that trace.causation_id must match envelope.causation_id."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_RESPONSE",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
            causation_id="MSG_PARENT01ABCDEFGHIJKLMNOPQR",
        )

        envelope["trace"]["causation_id"] = "MSG_DIFFERENT01ABCDEFGHIJKLMNOPQ"

        with pytest.raises(ValidationError, match="trace.causation_id must match envelope.causation_id"):
            validate(envelope)