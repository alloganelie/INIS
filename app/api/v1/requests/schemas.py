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
from app.governance.budget.quotas import Budget


class RequestBudget(BaseModel):
    """Per-dimension budget of a request (§41.2 ``[CONFIG]``)."""

    max_llm_tokens: int | None = Field(default=None, ge=0)
    max_web_requests: int | None = Field(default=None, ge=0)
    max_api_calls: int | None = Field(default=None, ge=0)
    max_storage_bytes: int | None = Field(default=None, ge=0)
    max_compute_seconds: int | None = Field(default=None, ge=0)
    max_total_cost_usd: float | None = Field(default=None, ge=0)

    def to_domain(self) -> Budget:
        """Return the domain :class:`Budget` value object."""
        return Budget(
            max_llm_tokens=self.max_llm_tokens,
            max_web_requests=self.max_web_requests,
            max_api_calls=self.max_api_calls,
            max_storage_bytes=self.max_storage_bytes,
            max_compute_seconds=self.max_compute_seconds,
            max_total_cost_usd=self.max_total_cost_usd,
        )


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
    #: §41.2 — per-dimension budget; ``None`` means unbounded.
    budget: RequestBudget | None = None
    #: §41.1 — TTL of the request; expiry delivers a PARTIAL_SUCCESS.
    ttl_seconds: int = Field(default=900, ge=1)


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
    #: §41.2 — the budget the request was created with. Exposed so an ingestion
    #: endpoint can enforce ``max_storage_bytes`` against the request itself
    #: instead of a global default the requester never agreed to.
    budget: RequestBudget | None = None
    status: str = "received"
    created_at: str | None = None
    pipeline_state: dict[str, Any] | None = None
    #: §41.2 — consumption report of this request.
    usage_report: dict[str, Any] | None = None
    #: §41.1 — resume projection of this request.
    resume_state: dict[str, Any] | None = None
