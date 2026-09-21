"""Domain entity for RBAC and ABAC access policies."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from ulid import ULID as PythonUlid


class AccessPolicy(BaseModel):
    """A policy defining a subject's authorized action on a resource."""

    policy_id: str
    subject: dict[str, Any]
    resource: dict[str, Any]
    action: Literal["read", "write", "update", "delete", "transmit", "search"]
    effect: Literal["allow", "deny"]
    conditions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, value: str) -> str:
        """Require the POL-prefixed ULID specified for access policies."""
        prefix = "POL_"
        if not isinstance(value, str) or not value.startswith(prefix):
            raise ValueError("policy_id must be a valid POL_ ULID")
        try:
            PythonUlid.from_str(value.removeprefix(prefix))
        except ValueError as exc:
            raise ValueError("policy_id must be a valid POL_ ULID") from exc
        return value

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Require the policy subject to identify an agent."""
        if not value.get("agent_id"):
            raise ValueError("subject requires agent_id")
        return value

    @field_validator("resource")
    @classmethod
    def validate_resource(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Require the resource type and classification required by §19.3."""
        missing = [key for key in ("type", "classification") if not value.get(key)]
        if missing:
            raise ValueError(f"resource requires {', '.join(missing)}")
        return value
