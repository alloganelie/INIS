"""Smoke tests for PHASE-01 foundations per §33."""

import pytest

from app.domain.entities.information_package import InformationPackage
from app.domain.value_objects.ulid import ULID
from app.messaging.protocol.envelope_builder import EnvelopeBuilder


@pytest.mark.skip(reason="api lot en cours")
def test_import_app_main() -> None:
    """Import app.main once Antigravity delivers the API entrypoint."""
    import app.main  # noqa: F401


def test_import_domain() -> None:
    import app.domain.entities  # noqa: F401


def test_import_storage() -> None:
    import app.storage.models  # noqa: F401


def test_import_messaging() -> None:
    import app.messaging.protocol  # noqa: F401


def test_ulid_roundtrip() -> None:
    identifier = ULID.new("REQ_")
    assert ULID.is_valid(identifier)


def test_envelope_build() -> None:
    builder = EnvelopeBuilder(
        default_sender_agent_id="agent-smoke",
        default_sender_agent_version="1.0.0",
    )
    envelope = builder.build(
        message_type="INFORMATION_REQUEST",
        recipient_agent_id="agent-target",
        payload={"query": "smoke"},
    )
    assert envelope["protocol_version"] == "1.0"
    assert envelope["message_id"].startswith("MSG_")
    assert envelope["message_type"] == "INFORMATION_REQUEST"


def test_information_package() -> None:
    package = InformationPackage(
        package_id=ULID.new("INF_"),
        request_id=ULID.new("REQ_"),
        units=[{"information_id": ULID.new("INF_")}],
        confidence={"score": 0.8},
        provenance={"source_id": ULID.new("SRC_")},
        data_stage="raw",
    )
    package.validate()
    assert package.provenance
