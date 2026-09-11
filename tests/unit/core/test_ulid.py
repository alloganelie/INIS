"""Tests for prefixed INIS ULID value objects."""

from app.domain.value_objects.ulid import ULID


def test_ulid_format() -> None:
    identifier = ULID.new("REQ_")

    assert identifier.startswith("REQ_")
    assert len(identifier) == len("REQ_") + 26
    assert ULID.is_valid(identifier)
