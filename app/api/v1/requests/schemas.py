"""Pydantic schemas for Information Requests per §7.

``RequestConstraints`` and ``RequiredOutput`` are the **wire** representation
of the §7 domain value objects. Their field names and default values are
sourced from :mod:`app.domain.value_objects.request_constraints` so the API
contract cannot drift away from the domain contract (see
``tests/unit/api/test_request_schema_defaults.py``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects.request_constraints import (
    DEFAULT_CONSTRAINTS,
    DEFAULT_REQUIRED_OUTPUT,
    OutputFormat,
)
from app.governance.budget.quotas import Budget
from app.storage.object_storage.object_storage_factory import split_storage_ref

#: §5.2/§9.1 — the only schemes a client may name as a source without multipart.
#: A local path would hand the API a read primitive over the host filesystem
#: (§19), and an ``http://`` reference would turn creation into an SSRF vector.
SOURCE_REF_SCHEMES: tuple[str, ...] = ("s3://",)


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
    #: §5.2/§9.1 — object already stored in the deployment's bucket, for clients
    #: that speak the protocol instead of HTTP multipart. Ingested **before** the
    #: run starts, so the request's plan sees the document it owns.
    source_ref: str | None = Field(
        default=None,
        description="Object already in the INIS bucket (s3://bucket/cle), §5.2",
    )

    @field_validator("source_ref")
    @classmethod
    def _validate_source_ref(cls, value: str | None) -> str | None:
        """Refuse a source reference INIS cannot read, naming why (§25.2).

        Raises:
            ValueError: When the reference is empty, names a scheme other than
                the accepted ones, or is not a complete ``s3://bucket/cle``.
        """
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            raise ValueError(
                "source_ref vide : omettre le champ, ou nommer un objet "
                "s3://bucket/chemin (§5.2)."
            )
        if not candidate.startswith(SOURCE_REF_SCHEMES):
            raise ValueError(
                f"source_ref refusée : schéma attendu {' ou '.join(SOURCE_REF_SCHEMES)} "
                f"(reçu : {candidate!r}). Un chemin local ou une URL HTTP n'est pas une "
                "source admissible (§9.1, §19)."
            )
        if split_storage_ref(candidate) is None:
            raise ValueError(
                f"source_ref incomplète : attendu s3://bucket/chemin (reçu : {candidate!r})."
            )
        return candidate


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
