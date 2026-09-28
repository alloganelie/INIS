"""Unit tests for §41.11 protocol versioning and compatibility."""

import pytest

from app.core.errors import ValidationError
from app.messaging.handlers.agent_register_handler import AgentRegisterHandler
from app.messaging.protocol.envelope_builder import EnvelopeBuilder
from app.messaging.protocol.envelope_validator import validate
from app.messaging.protocol.versioning import PROTOCOL_COMPATIBILITY
from app.messaging.protocol.versioning import ProtocolCompatibility
from app.messaging.protocol.versioning import parse_version


def _envelope() -> dict:
    builder = EnvelopeBuilder(
        default_sender_agent_id="agent-123",
        default_sender_agent_version="1.0.0",
    )
    return builder.build(
        message_type="AGENT_REGISTER",
        recipient_agent_id="registry",
        payload={},
    )


class TestProtocolCompatibility:
    """parse_version + the protocol_compatibility [CONFIG] block."""

    def test_parse_version(self) -> None:
        assert parse_version("1.0") == (1, 0)
        assert parse_version("2.13") == (2, 13)
        with pytest.raises(ValueError, match="malformed"):
            parse_version("1")
        with pytest.raises(ValueError, match="string"):
            parse_version(1.0)

    def test_to_dict_matches_the_spec_block(self) -> None:
        assert PROTOCOL_COMPATIBILITY.to_dict() == {
            "protocol_compatibility": {
                "supported_versions": ["1.0", "1.1"],
                "preferred_version": "1.0",
                "min_version": "1.0",
            }
        }

    def test_is_compatible_applies_the_major_window(self) -> None:
        compat = PROTOCOL_COMPATIBILITY
        # Forward tolerance: newer minor of a known major.
        assert compat.is_compatible("1.0") is True
        assert compat.is_compatible("1.1") is True
        assert compat.is_compatible("1.9") is True
        # Incompatible majors / malformed input.
        assert compat.is_compatible("2.0") is False
        assert compat.is_compatible("0.9") is False
        assert compat.is_compatible("nope") is False
        assert compat.is_compatible(None) is False

    def test_invalid_configuration_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="preferred_version"):
            ProtocolCompatibility(supported_versions=("1.0",), preferred_version="1.1")
        with pytest.raises(ValueError, match="min_version"):
            ProtocolCompatibility(
                supported_versions=("1.1",),
                preferred_version="1.1",
                min_version="1.0",
            )
        with pytest.raises(ValueError, match="empty"):
            ProtocolCompatibility(supported_versions=())

    def test_negotiate_prefers_our_preferred_version(self) -> None:
        compat = PROTOCOL_COMPATIBILITY
        assert compat.negotiate(["1.0", "1.1"]) == "1.0"
        assert compat.negotiate(["1.1"]) == "1.1"
        assert compat.negotiate(["1.0"]) == "1.0"
        assert compat.negotiate(["2.0"]) is None
        assert compat.negotiate([]) is None
        assert compat.negotiate(None) is None


class TestValidatorTolerance:
    """Forward / backward / rejection rules of §41.11 on envelopes."""

    def test_forward_tolerance_accepts_newer_minor_and_ignores_unknown_fields(self) -> None:
        envelope = _envelope()
        envelope["protocol_version"] = "1.1"
        envelope["future_field"] = {"unknown": True}
        envelope["payload"]["future_payload_key"] = 42
        validate(envelope)  # must not raise

    def test_backward_tolerance_defaults_a_missing_version(self) -> None:
        envelope = _envelope()
        del envelope["protocol_version"]
        validate(envelope)  # must not raise

    def test_incompatible_major_is_rejected_with_version_supported(self) -> None:
        envelope = _envelope()
        envelope["protocol_version"] = "2.0"
        with pytest.raises(ValidationError, match="version_supported"):
            validate(envelope)


class TestAgentRegisterNegotiation:
    """Négociation lors du AGENT_REGISTER (§41.11)."""

    def test_negotiates_from_declared_versions(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()
        envelope["payload"]["supported_protocol_versions"] = ["1.0", "1.1"]

        chosen = handler.negotiate(envelope)

        assert chosen == "1.0"
        assert handler.negotiated("agent-123") == "1.0"

    def test_agent_declaring_only_11_gets_11(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()
        envelope["payload"]["supported_protocol_versions"] = ["1.1"]

        assert handler.negotiate(envelope) == "1.1"

    def test_legacy_agent_falls_back_to_its_envelope_version(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()  # no declaration → protocol_version "1.0"

        assert handler.negotiate(envelope) == "1.0"
        assert handler.negotiated_versions == {"agent-123": "1.0"}

    def test_no_common_version_is_rejected_with_version_supported(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()
        envelope["payload"]["supported_protocol_versions"] = ["2.0", "3.1"]

        with pytest.raises(ValidationError, match="version_supported"):
            handler.negotiate(envelope)
        assert handler.negotiated("agent-123") is None

    def test_malformed_declaration_fails_explicitly(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()
        envelope["payload"]["supported_protocol_versions"] = "1.0"

        with pytest.raises(ValueError, match="supported_protocol_versions"):
            handler.negotiate(envelope)

    @pytest.mark.asyncio
    async def test_handler_is_callable_as_a_message_handler(self) -> None:
        handler = AgentRegisterHandler()
        envelope = _envelope()
        envelope["payload"]["supported_protocol_versions"] = ["1.1"]

        assert await handler(envelope) == "1.1"
