"""Pydantic schemas for Agent Identity per §6."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentIdentity(BaseModel):
    """Identity card and capabilities of an agent in the registry."""

    agent_id: str = Field(..., min_length=1, description="Unique agent identifier")
    name: str = Field(..., min_length=1, description="Human-readable agent name")
    description: str = Field(default="", description="Functional description")
    version: str = Field(default="0.1.0", description="Semver version string")
    status: Literal["available", "degraded", "unavailable", "maintenance"] = "available"
    capabilities: list[str] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=lambda: ["http"])
    message_types: list[str] = Field(default_factory=list)
    input_schemas: list[dict[str, Any]] = Field(default_factory=list)
    output_schemas: list[dict[str, Any]] = Field(default_factory=list)
    security_requirements: list[str] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)
    performance_profile: dict[str, Any] = Field(default_factory=dict)
    learning_profile: dict[str, Any] = Field(default_factory=dict)
    registered_at: str | None = None
    last_seen_at: str | None = None
