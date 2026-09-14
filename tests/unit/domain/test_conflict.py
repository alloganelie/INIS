"""Tests for the Conflict domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities import Conflict
from app.domain.value_objects.ulid import ULID


def make_conflict(**overrides: object) -> Conflict:
    """Build a valid Conflict, allowing one field to be overridden."""
    values: dict[str, object] = {
        "conflict_id": ULID.new("CONFLICT_"),
        "information_a": ULID.new("INF_"),
        "information_b": ULID.new("INF_"),
        "difference_type": "value",
        "severity": "medium",
        "resolution_status": "open",
    }
    values.update(overrides)
    return Conflict(**values)


def test_conflict_accepts_specification_values() -> None:
    """A valid §14.3 conflict preserves its empty evidence list."""
    conflict = make_conflict()

    assert conflict.resolution_evidence == []
    assert conflict.difference_type == "value"


def test_conflict_rejects_invalid_conflict_identifier() -> None:
    """Conflict IDs must use the canonical CONFLICT_ ULID format."""
    with pytest.raises(ValidationError, match="CONFLICT_"):
        make_conflict(conflict_id="CONFLICT_invalid")


def test_conflict_rejects_non_information_identifier() -> None:
    """Both conflict sides must identify information units."""
    with pytest.raises(ValidationError, match="INF_"):
        make_conflict(information_a=ULID.new("SRC_"))
