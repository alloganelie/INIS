"""Unit tests for the §7/§0.3 domain value objects.

Covers :class:`~app.domain.value_objects.ulid.ULID` (prefixed identifiers,
§0.3), :class:`~app.domain.value_objects.email.Email` (§19.4 contact data) and
the §7 request constraints / required-output contracts shared with the API
wire schemas.
"""

from __future__ import annotations

import time

import pytest

from app.core.constants import ULID_PREFIXES
from app.domain.value_objects.email import Email
from app.domain.value_objects.request_constraints import (
    DEFAULT_CONSTRAINTS,
    DEFAULT_REQUIRED_OUTPUT,
    RequestConstraints,
    RequiredOutput,
)
from app.domain.value_objects.ulid import ULID


class TestULIDPrefixes:
    """§0.3 — every identifier uses one of the approved prefixes."""

    def test_registry_covers_the_spec_prefixes(self) -> None:
        """The §0.3 registry is present and non-empty."""
        for prefix in ("REQ_", "SRC_", "INF_", "EVID_", "AUD_"):
            assert prefix in ULID_PREFIXES

    def test_new_prefixes_the_suffix_with_a_business_prefix(self) -> None:
        """A generated id starts with its prefix and carries a 26-char ULID."""
        identifier = ULID.new("EVID_")
        assert identifier.startswith("EVID_")
        suffix = identifier.removeprefix("EVID_")
        assert len(suffix) == 26
        assert suffix.isalnum()

    def test_new_rejects_an_unsupported_prefix(self) -> None:
        """An unknown prefix is refused instead of producing a fake id."""
        with pytest.raises(ValueError, match="Unsupported ULID prefix"):
            ULID.new("XXX_")


class TestULIDValidation:
    """§0.3 — ``is_valid`` is the single validation entry point."""

    def test_generated_identifier_is_valid(self) -> None:
        """Round-trip: everything ``new`` produces is accepted by ``is_valid``."""
        assert ULID.is_valid(ULID.new("REQ_")) is True

    def test_missing_prefix_is_invalid(self) -> None:
        """A bare suffix carries no zone information and is rejected."""
        assert ULID.is_valid("00000000000000000000000000") is False

    def test_wrong_suffix_length_is_invalid(self) -> None:
        """A 25-character suffix is not a ULID."""
        assert ULID.is_valid("REQ_" + "0" * 25) is False

    def test_non_base32_suffix_is_invalid(self) -> None:
        """Crockford base32 rejects ``I``; the identifier must not validate."""
        assert ULID.is_valid("REQ_" + "I" * 26) is False

    def test_non_string_is_invalid(self) -> None:
        """Non-string input never raises, it just fails validation."""
        assert ULID.is_valid(None) is False  # type: ignore[arg-type]


class TestULIDOrdering:
    """§0.3 — identifiers sort lexicographically by creation time."""

    def test_later_identifier_sorts_after_earlier_one(self) -> None:
        """The 48-bit timestamp prefix makes string ordering chronological."""
        first = ULID.new("REQ_")
        time.sleep(0.003)
        second = ULID.new("REQ_")
        assert first < second

    def test_two_identifiers_differ(self) -> None:
        """Two calls never collide (randomness in the suffix)."""
        assert ULID.new("REQ_") != ULID.new("REQ_")


class TestEmail:
    """§19.4 — contact data is validated before it is stored."""

    def test_valid_address_is_kept_verbatim(self) -> None:
        """A valid address is serializable through ``str``."""
        assert str(Email("agent@example.com")) == "agent@example.com"

    @pytest.mark.parametrize(
        "value",
        ["not-an-email", "a@b", "@example.com", "user@.com", "", "user @example.com"],
    )
    def test_invalid_addresses_are_rejected(self, value: str) -> None:
        """Malformed addresses raise ``ValueError`` at construction."""
        with pytest.raises(ValueError, match="valid email address"):
            Email(value)

    def test_frozen_value_object(self) -> None:
        """Value objects are immutable (§0.2)."""
        address = Email("agent@example.com")
        with pytest.raises(Exception):
            address.value = "other@example.com"  # type: ignore[misc]


class TestRequestConstraints:
    """§7 — the documented defaults are the contract with the API schemas."""

    def test_defaults_match_the_spec(self) -> None:
        """Defaults are the ones published by ``RequestConstraints``."""
        constraints = RequestConstraints()
        assert constraints.minimum_confidence == 0.8
        assert constraints.maximum_execution_time_seconds == 300
        assert constraints.maximum_iterations == 12
        assert constraints.maximum_web_depth == 3
        assert constraints.maximum_cost is None
        assert constraints.date_range is None
        assert constraints.source_preferences == ()

    def test_explicit_values_are_preserved(self) -> None:
        """Callers can override every bound."""
        constraints = RequestConstraints(
            minimum_confidence=0.95,
            maximum_cost=2.5,
            maximum_iterations=3,
            maximum_web_depth=1,
            source_preferences=("https://example.com",),
        )
        assert constraints.minimum_confidence == 0.95
        assert constraints.maximum_cost == 2.5
        assert constraints.maximum_iterations == 3
        assert constraints.maximum_web_depth == 1
        assert constraints.source_preferences == ("https://example.com",)

    def test_default_instance_is_the_canonical_shared_instance(self) -> None:
        """``DEFAULT_CONSTRAINTS`` stays equal to a fresh instance."""
        assert DEFAULT_CONSTRAINTS == RequestConstraints()

    def test_constraints_are_frozen(self) -> None:
        """Mutating a shared default would corrupt every later request."""
        with pytest.raises(Exception):
            DEFAULT_CONSTRAINTS.minimum_confidence = 0.1  # type: ignore[misc]


class TestRequiredOutput:
    """§24 — the delivery format contract."""

    def test_default_format_is_the_evidence_package(self) -> None:
        """``evidence_package`` is the default output of §24."""
        assert RequiredOutput().format == "evidence_package"
        assert RequiredOutput().fields == ()

    def test_format_and_fields_round_trip(self) -> None:
        """Explicit format/fields are preserved."""
        output = RequiredOutput(format="csv", fields=("title", "url"))
        assert output.format == "csv"
        assert output.fields == ("title", "url")

    def test_default_instance_is_the_canonical_shared_instance(self) -> None:
        """``DEFAULT_REQUIRED_OUTPUT`` stays equal to a fresh instance."""
        assert DEFAULT_REQUIRED_OUTPUT == RequiredOutput()

