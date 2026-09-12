"""Pydantic schemas for Information Requests per §7."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RequestConstraints(BaseModel):
    """Execution constraints for an InformationRequest."""

    date_range: dict[str, Any] | None = None
    source_preferences: list[str] = Field(default_factory=list)
    minimum_confidence: float = Field(0.8, ge=0.0, le=1.0)
    maximum_cost: float | None = None
    maximum_execution_time_seconds: int = 300
    maximum_iterations: int = 12
    maximum_web_depth: int = 3


class RequiredOutput(BaseModel):
    """Required format and fields for the request delivery."""

    format: Literal[
        "evidence_package",
        "json",
        "csv",
        "xlsx",
        "pdf",
        "xml",
    ] = "evidence_package"
    fields: list[str] = Field(default_factory=list)


class InformationRequestCreate(BaseModel):
    """Payload to submit a new InformationRequest."""

    objective: str = Field(..., min_length=1, description="Primary research objective")
    request_type: Literal[
        "research",
        "source",
        "evidence",
        "data",
        "artifact",
    ] = "research"
    question: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    required_information: list[str] = Field(default_factory=list)
    constraints: RequestConstraints = Field(default_factory=RequestConstraints)
    required_output: RequiredOutput = Field(default_factory=RequiredOutput)
    requester: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)


class InformationRequestResponse(BaseModel):
    """Representation of an active or stored InformationRequest."""

    request_id: str
    request_type: Literal[
        "research",
        "source",
        "evidence",
        "data",
        "artifact",
    ] = "research"
    objective: str
    question: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    required_information: list[str] = Field(default_factory=list)
    constraints: RequestConstraints = Field(default_factory=RequestConstraints)
    required_output: RequiredOutput = Field(default_factory=RequiredOutput)
    requester: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    status: str = "received"
    created_at: str | None = None
