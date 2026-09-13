"""Pydantic schemas for Sources per §9 and §32."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Payload to register a new Source."""

    name: str = Field(..., min_length=1, description="Human-readable source name")
    source_type: str = Field(..., min_length=1, description="Source connector type (e.g. rest_api, web_page, postgres)")
    url: str | None = Field(default=None, description="Source URI or network endpoint")
    description: str | None = Field(default=None, description="Functional summary of the source")
    trust_level: float = Field(default=1.0, ge=0.0, le=1.0, description="Base trustworthiness score between 0.0 and 1.0")
    status: str = Field(default="active", description="Operational status: active, archived, deleted, superseded")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary connector or source metadata")


class SourceResponse(BaseModel):
    """Representation of an active or stored Source."""

    source_id: str = Field(..., description="Canonical SRC_ prefixed ULID")
    name: str
    source_type: str
    url: str | None = None
    description: str | None = None
    trust_level: float = 1.0
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class SourceList(BaseModel):
    """List container for sources."""

    sources: list[SourceResponse] = Field(default_factory=list)
    items: list[SourceResponse] = Field(default_factory=list)
    total: int = 0

    def __init__(self, **data: Any) -> None:
        if "sources" in data and "items" not in data:
            data["items"] = data["sources"]
        elif "items" in data and "sources" not in data:
            data["sources"] = data["items"]
        if "total" not in data:
            data["total"] = len(data.get("sources", []))
        super().__init__(**data)
