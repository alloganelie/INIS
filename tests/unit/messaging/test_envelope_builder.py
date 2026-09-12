"""Tests for EnvelopeBuilder per §5.1."""

import pytest

from app.messaging.protocol.envelope_builder import EnvelopeBuilder
from app.messaging.protocol.envelope_validator import validate


class TestEnvelopeBuilder:
    """Tests for EnvelopeBuilder.build()."""

    def test_build_valid_envelope(self) -> None:
        """Test that a valid envelope is built with all required fields."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
            default_sender_agent_instance_id="INST_01ABC123",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test query"},
        )

        # Required top-level fields
        assert envelope["protocol_version"] == "1.0"
        assert envelope["message_id"].startswith("MSG_")
        assert envelope["correlation_id"].startswith("CORR_")
        assert envelope["causation_id"] is None
        assert envelope["timestamp"].endswith("Z")
        assert "sender" in envelope
        assert "recipient" in envelope
        assert envelope["message_type"] == "INFORMATION_REQUEST"
        assert envelope["priority"] == "normal"
        assert envelope["reply_to"] is None
        assert envelope["ttl_seconds"] == 300
        assert envelope["payload"] == {"query": "test query"}
        assert "security" in envelope
        assert "trace" in envelope

        # Sender structure
        assert envelope["sender"]["agent_id"] == "agent-123"
        assert envelope["sender"]["agent_instance_id"] == "INST_01ABC123"
        assert envelope["sender"]["agent_version"] == "1.0.0"

        # Recipient structure
        assert envelope["recipient"]["agent_id"] == "agent-456"
        assert envelope["recipient"]["agent_instance_id"] is None

        # Security structure
        assert envelope["security"]["auth_method"] == "mtls"
        assert envelope["security"]["token_id"] is None
        assert envelope["security"]["scopes"] == []

        # Trace structure
        assert len(envelope["trace"]["trace_id"]) == 32
        assert len(envelope["trace"]["span_id"]) == 16
        assert envelope["trace"]["correlation_id"] == envelope["correlation_id"]
        assert envelope["trace"]["causation_id"] is None

        # Should pass validation
        validate(envelope)

    def test_envelope_has_ulid_message_id(self) -> None:
        """Test that message_id uses MSG_ ULID prefix."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="AGENT_REGISTER",
            recipient_agent_id="registry",
            payload={},
        )

        assert envelope["message_id"].startswith("MSG_")
        assert len(envelope["message_id"]) == 4 + 26  # "MSG_" + 26-char ULID

    def test_envelope_has_ulid_correlation_id(self) -> None:
        """Test that correlation_id uses CORR_ ULID prefix."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="AGENT_REGISTER",
            recipient_agent_id="registry",
            payload={},
        )

        assert envelope["correlation_id"].startswith("CORR_")
        assert len(envelope["correlation_id"]) == 5 + 26  # "CORR_" + 26-char ULID

    def test_custom_correlation_id_used(self) -> None:
        """Test that a provided correlation_id is used instead of generating one."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        custom_corr = "CORR_01ABCDEFGHIJKLMNOPQRSTUV"
        envelope = builder.build(
            message_type="AGENT_REGISTER",
            recipient_agent_id="registry",
            payload={},
            correlation_id=custom_corr,
        )

        assert envelope["correlation_id"] == custom_corr
        assert envelope["trace"]["correlation_id"] == custom_corr

    def test_custom_causation_id(self) -> None:
        """Test that causation_id is set when provided."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        parent_msg_id = "MSG_01ABCDEFGHIJKLMNOPQRSTUV"
        envelope = builder.build(
            message_type="INFORMATION_RESPONSE",
            recipient_agent_id="agent-456",
            payload={},
            causation_id=parent_msg_id,
        )

        assert envelope["causation_id"] == parent_msg_id
        assert envelope["trace"]["causation_id"] == parent_msg_id

    def test_priority_options(self) -> None:
        """Test all valid priority levels."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        for priority in ("low", "normal", "high", "critical"):
            envelope = builder.build(
                message_type="AGENT_HEARTBEAT",
                recipient_agent_id="registry",
                payload={},
                priority=priority,
            )
            assert envelope["priority"] == priority

    def test_invalid_priority_raises(self) -> None:
        """Test that invalid priority raises ValueError."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid priority"):
            builder.build(
                message_type="AGENT_HEARTBEAT",
                recipient_agent_id="registry",
                payload={},
                priority="urgent",
            )

    def test_invalid_message_type_raises(self) -> None:
        """Test that invalid message_type raises ValueError."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid message_type"):
            builder.build(
                message_type="INVALID_TYPE",
                recipient_agent_id="registry",
                payload={},
            )

    def test_invalid_auth_method_raises(self) -> None:
        """Test that invalid auth_method raises ValueError."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid auth_method"):
            builder.build(
                message_type="AGENT_REGISTER",
                recipient_agent_id="registry",
                payload={},
                security_auth_method="oauth",
            )

    def test_ttl_must_be_positive(self) -> None:
        """Test that ttl_seconds must be positive."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        with pytest.raises(ValueError, match="ttl_seconds must be positive"):
            builder.build(
                message_type="AGENT_REGISTER",
                recipient_agent_id="registry",
                payload={},
                ttl_seconds=0,
            )

    def test_override_sender_fields(self) -> None:
        """Test that sender fields can be overridden per-call."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
            default_sender_agent_instance_id="INST_DEFAULT",
        )

        envelope = builder.build(
            message_type="AGENT_REGISTER",
            recipient_agent_id="registry",
            payload={},
            sender_agent_id="agent-999",
            sender_agent_version="2.0.0",
            sender_agent_instance_id="INST_OVERRIDE",
        )

        assert envelope["sender"]["agent_id"] == "agent-999"
        assert envelope["sender"]["agent_version"] == "2.0.0"
        assert envelope["sender"]["agent_instance_id"] == "INST_OVERRIDE"

    def test_recipient_instance_id(self) -> None:
        """Test that recipient agent_instance_id can be set."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="AGENT_REGISTER",
            recipient_agent_id="registry",
            payload={},
            recipient_agent_instance_id="INST_TARGET",
        )

        assert envelope["recipient"]["agent_instance_id"] == "INST_TARGET"

    def test_reply_to_and_security_fields(self) -> None:
        """Test reply_to, token_id, and scopes fields."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        envelope = builder.build(
            message_type="INFORMATION_REQUEST",
            recipient_agent_id="agent-456",
            payload={"query": "test"},
            reply_to="queue.reply.123",
            security_token_id="token-abc",
            security_scopes=["read", "write"],
        )

        assert envelope["reply_to"] == "queue.reply.123"
        assert envelope["security"]["token_id"] == "token-abc"
        assert envelope["security"]["scopes"] == ["read", "write"]

    def test_all_message_types_valid(self) -> None:
        """Test that all V1 message types from §5.2 are accepted."""
        builder = EnvelopeBuilder(
            default_sender_agent_id="agent-123",
            default_sender_agent_version="1.0.0",
        )

        valid_types = [
            "AGENT_REGISTER", "AGENT_UPDATE", "AGENT_HEARTBEAT",
            "CAPABILITY_QUERY", "INFORMATION_REQUEST", "INFORMATION_RESPONSE",
            "SOURCE_REQUEST", "EVIDENCE_REQUEST", "DATA_REQUEST",
            "RESEARCH_REQUEST", "RESEARCH_PROGRESS", "RESEARCH_COMPLETED",
            "AGENT_DELEGATION_REQUEST", "AGENT_DELEGATION_RESPONSE",
            "CLARIFICATION_REQUEST", "CONFLICT_REPORT", "LOW_CONFIDENCE_REPORT",
            "ACCESS_DENIED", "VALIDATION_ERROR", "EXECUTION_ERROR",
            "CANCEL_REQUEST", "CANCELLED", "AUDIT_EVENT",
        ]

        for msg_type in valid_types:
            envelope = builder.build(
                message_type=msg_type,
                recipient_agent_id="target",
                payload={},
            )
            assert envelope["message_type"] == msg_type
            validate(envelope)