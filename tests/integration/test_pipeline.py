"""End-to-end smoke for PHASE-01 coexistence of protocol and domain objects."""

from app.domain.entities.information_package import InformationPackage
from app.domain.value_objects.ulid import ULID
from app.messaging.protocol.envelope_builder import EnvelopeBuilder


async def test_end_to_end_smoke() -> None:
    request_id = ULID.new("REQ_")
    builder = EnvelopeBuilder(
        default_sender_agent_id="agent-pipeline",
        default_sender_agent_version="1.0.0",
    )
    envelope = builder.build(
        message_type="INFORMATION_REQUEST",
        recipient_agent_id="agent-target",
        payload={"request_id": request_id},
        correlation_id=ULID.new("CORR_"),
    )
    package = InformationPackage(
        package_id=ULID.new("INF_"),
        request_id=request_id,
        units=[{"information_id": ULID.new("INF_")}],
        confidence={"score": 0.8},
        provenance={"source_id": ULID.new("SRC_")},
        data_stage="raw",
    )
    package.validate()

    assert envelope["payload"]["request_id"] == package.request_id
    assert envelope["message_id"] != package.package_id
    assert ULID.is_valid(envelope["message_id"])
    assert ULID.is_valid(package.package_id)
    assert package.provenance
