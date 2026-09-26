"""Verify API wire schemas mirror the domain §7 contract without drift."""

from app.api.v1.requests.schemas import RequestConstraints as WireConstraints
from app.api.v1.requests.schemas import RequiredOutput as WireOutput
from app.domain.value_objects.request_constraints import (
    DEFAULT_CONSTRAINTS,
    DEFAULT_REQUIRED_OUTPUT,
    RequestConstraints as DomainConstraints,
    RequiredOutput as DomainOutput,
)


def test_wire_constraints_defaults_match_domain() -> None:
    wire = WireConstraints()
    domain = DomainConstraints()

    assert wire.date_range == domain.date_range
    assert wire.source_preferences == list(domain.source_preferences)
    assert wire.minimum_confidence == domain.minimum_confidence
    assert wire.maximum_cost == domain.maximum_cost
    assert wire.maximum_execution_time_seconds == domain.maximum_execution_time_seconds
    assert wire.maximum_iterations == domain.maximum_iterations
    assert wire.maximum_web_depth == domain.maximum_web_depth


def test_wire_required_output_defaults_match_domain() -> None:
    wire = WireOutput()
    domain = DomainOutput()

    assert wire.format == domain.format
    assert wire.fields == list(domain.fields)


def test_default_constants_are_frozen_and_valid() -> None:
    assert DEFAULT_CONSTRAINTS.minimum_confidence == 0.8
    assert DEFAULT_REQUIRED_OUTPUT.format == "evidence_package"
