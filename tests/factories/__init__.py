"""Deterministic domain builders shared by the INIS test suite (§33.2).

Each module owns one aggregate from ``app/domain/entities`` and exposes two
entry points:

* ``make_<entity>(**overrides)`` — a valid instance/dict, override any attribute
  to build the edge case a test needs;
* identifiers are always produced through :class:`~app.domain.value_objects.ULID`
  so no test can invent an identifier that violates §0.3.

The builders are pure: no I/O, no database, no clock side effects beyond the
entity defaults. That is what lets an agentic scenario (§33.3) and a repository
test (§27) share the same material.
"""

from tests.factories.agent_factory import make_agent_identity, make_agent_identity_dict
from tests.factories.artifact_factory import make_artifact, make_artifact_version
from tests.factories.audit_event_factory import make_audit_event
from tests.factories.claim_factory import make_claim
from tests.factories.conflict_factory import make_conflict
from tests.factories.dataset_factory import make_dataset
from tests.factories.document_factory import make_document
from tests.factories.evidence_factory import make_evidence
from tests.factories.information_unit_factory import make_information_unit
from tests.factories.request_factory import make_request_payload
from tests.factories.source_factory import make_source, make_source_create_payload
from tests.factories.transformation_factory import make_transformation

__all__ = [
    "make_agent_identity",
    "make_agent_identity_dict",
    "make_artifact",
    "make_artifact_version",
    "make_audit_event",
    "make_claim",
    "make_conflict",
    "make_dataset",
    "make_document",
    "make_evidence",
    "make_information_unit",
    "make_request_payload",
    "make_source",
    "make_source_create_payload",
    "make_transformation",
]

