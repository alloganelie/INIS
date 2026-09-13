"""Pydantic schemas for Conflicts per §14.3 and §32."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConflictCreate(BaseModel):
    """Payload to record a detected conflict/contradiction."""

    information_a: str | None = Field(default=None, description="First contradictory information ID (INF_...)")
    information_b: str | None = Field(default=None, description="Second contradictory information ID (INF_...)")
    information_ids: list[str] = Field(default_factory=list, description="List of contradictory information IDs")
    claim_ids: list[str] = Field(default_factory=list, description="Contradictory claim IDs")
    difference_type: Literal[
        "value",
        "definition",
        "date",
        "methodology",
        "scope",
    ] = "value"
    severity: Literal["low", "medium", "high"] = "medium"
    status: Literal["open", "investigated", "unresolved", "resolved"] = "open"
    resolution_status: Literal["open", "investigated", "unresolved", "resolved"] = "open"
    description: str | None = Field(default=None, description="Human readable description of the conflict")
    resolution_evidence: list[str] = Field(default_factory=list, description="Evidence resolving the contradiction")

    def __init__(self, **data: Any) -> None:
        if "status" in data and "resolution_status" not in data:
            data["resolution_status"] = data["status"]
        elif "resolution_status" in data and "status" not in data:
            data["status"] = data["resolution_status"]
        super().__init__(**data)


class ConflictResponse(BaseModel):
    """Full representation of a Conflict per §14.3."""

    conflict_id: str = Field(..., description="Canonical CONFLICT_ prefixed ULID")
    information_a: str | None = None
    information_b: str | None = None
    information_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    difference_type: str = "value"
    severity: str = "medium"
    status: str = "open"
    resolution_status: str = "open"
    description: str | None = None
    resolution_evidence: list[str] = Field(default_factory=list)
    detected_at: str | None = None


class ConflictList(BaseModel):
    """Container for a list of conflicts."""

    items: list[ConflictResponse] = Field(default_factory=list)
    conflicts: list[ConflictResponse] = Field(default_factory=list)
    total: int = 0

    def __init__(self, **data: Any) -> None:
        if "items" in data and "conflicts" not in data:
            data["conflicts"] = data["items"]
        elif "conflicts" in data and "items" not in data:
            data["items"] = data["conflicts"]
        if "total" not in data:
            data["total"] = len(data.get("items", []))
        super().__init__(**data)
