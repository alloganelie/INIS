"""Pydantic schemas for Information Requests per §7.

``RequestConstraints`` and ``RequiredOutput`` are the **wire** representation
of the §7 domain value objects. Their field names and default values are
sourced from :mod:`app.domain.value_objects.request_constraints` so the API
contract cannot drift away from the domain contract (see
``tests/unit/api/test_request_schema_defaults.py``).
"""

from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.value_objects.request_constraints import DEFAULT_CONSTRAINTS
from app.domain.value_objects.request_constraints import DEFAULT_REQUIRED_OUTPUT
from app.domain.value_objects.request_constraints import OutputFormat


class RequestConstraints(BaseModel):
    """Wire representation of the §7 execution constraints."""

    date_range: dict[str, Any] | None = DEFAULT_CONSTRAINTS.date_range
    source_preferences: list[str] = Field(default_factory=list)
    minimum_confidence: float = Field(
        DEFAULT_CONSTRAINTS.minimum_confidence, ge=0.0, le=1.0
    )
    maximum_cost: float | None = DEFAULT_CONSTRAINTS.maximum_cost
    maximum_execution_time_seconds: int = DEFAULT_CONSTRAINTS.maximum_execution_time_seconds
    maximum_iterations: int = DEFAULT_CONSTRAINTS.maximum_iterations
    maximum_web_depth: int = DEFAULT_CONSTRAINTS.maximum_web_depth


class RequiredOutput(BaseModel):
    """Wire representation of the §7 required delivery format."""

    format: OutputFormat = DEFAULT_REQUIRED_OUTPUT.format
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
    pipeline_state: dict[str, Any] | None = None
