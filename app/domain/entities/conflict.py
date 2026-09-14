"""Domain entity for contradictions between information units."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects.ulid import ULID


class Conflict(BaseModel):
    """A contradiction detected between two traceable information units."""

    conflict_id: str
    information_a: str
    information_b: str
    difference_type: Literal["value", "definition", "date", "methodology", "scope"]
    severity: Literal["low", "medium", "high"]
    resolution_status: Literal["open", "investigated", "unresolved", "resolved"]
    resolution_evidence: list[Any] = Field(default_factory=list)

    @field_validator("conflict_id")
    @classmethod
    def validate_conflict_id(cls, value: str) -> str:
        """Require the canonical CONFLICT-prefixed ULID identifier."""
        if not value.startswith("CONFLICT_") or not ULID.is_valid(value):
            raise ValueError("conflict_id must be a valid CONFLICT_ ULID")
        return value

    @field_validator("information_a", "information_b")
    @classmethod
    def validate_information_id(cls, value: str) -> str:
        """Require a canonical INF-prefixed information identifier."""
        if not value.startswith("INF_") or not ULID.is_valid(value):
            raise ValueError("information IDs must be valid INF_ ULIDs")
        return value
