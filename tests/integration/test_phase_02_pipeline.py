"""PHASE-02 pipeline smoke: request identifier packed into an Envelope."""

from app.domain.value_objects.ulid import ULID
from app.messaging.protocol.envelope_builder import EnvelopeBuilder


def test_request_to_envelope() -> None:
    request_id = ULID.new("REQ_")
    builder = EnvelopeBuilder(
        default_sender_agent_id="agent-phase-02",
        default_sender_agent_version="1.0.0",
    )
    envelope = builder.build(
        message_type="INFORMATION_REQUEST",
        recipient_agent_id="inis-runtime",
        payload={"request_id": request_id},
        correlation_id=ULID.new("CORR_"),
    )

    assert ULID.is_valid(request_id)
    assert envelope["payload"]["request_id"] == request_id
    assert envelope["message_type"] == "INFORMATION_REQUEST"
    assert ULID.is_valid(envelope["message_id"])
    assert ULID.is_valid(envelope["correlation_id"])
    assert envelope["protocol_version"] == "1.0"
