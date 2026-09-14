"""Tests for the AccessPolicy domain entity."""

import pytest
from pydantic import ValidationError
from ulid import ULID as PythonUlid

from app.domain.entities import AccessPolicy


def policy_id() -> str:
    """Build a valid policy identifier defined by §19.3."""
    return f"POL_{PythonUlid()}"


def make_policy(**overrides: object) -> AccessPolicy:
    """Build a valid policy, allowing individual fields to be overridden."""
    values: dict[str, object] = {
        "policy_id": policy_id(),
        "subject": {"agent_id": "agent-1"},
        "resource": {"type": "document", "classification": "internal"},
        "action": "read",
        "effect": "allow",
    }
    values.update(overrides)
    return AccessPolicy(**values)


def test_access_policy_accepts_specification_fields() -> None:
    """A §19.3 policy retains its empty default conditions."""
    policy = make_policy()

    assert policy.conditions == {}
    assert policy.effect == "allow"


def test_access_policy_rejects_invalid_policy_id() -> None:
    """Policy identifiers must have a valid POL_ ULID suffix."""
    with pytest.raises(ValidationError, match="POL_"):
        make_policy(policy_id="POL_invalid")


def test_access_policy_requires_agent_subject() -> None:
    """Policies must identify their agent subject."""
    with pytest.raises(ValidationError, match="agent_id"):
        make_policy(subject={})


def test_access_policy_requires_classified_resource() -> None:
    """Policies must identify both resource type and classification."""
    with pytest.raises(ValidationError, match="classification"):
        make_policy(resource={"type": "document"})
