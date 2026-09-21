"""Parse a free-text request into the INIS section 7 request contract."""

from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID


RequestType = Literal["research", "source", "evidence", "data", "artifact"]


@dataclass(frozen=True)
class RequestConstraints:
    """Execution limits carried by an information request."""

    date_range: dict[str, Any] | None = None
    source_preferences: tuple[str, ...] = ()
    minimum_confidence: float = 0.8
    maximum_cost: float | None = None
    maximum_execution_time_seconds: int = 300
    maximum_iterations: int = 12
    maximum_web_depth: int = 3


@dataclass(frozen=True)
class RequiredOutput:
    """Requested delivery format and optional fields."""

    format: Literal["evidence_package", "json", "csv", "xlsx", "pdf", "xml"] = (
        "evidence_package"
    )
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class InformationRequest:
    """Structured representation of a request according to INIS section 7."""

    request_id: str
    request_type: RequestType
    objective: str
    question: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    required_information: tuple[str, ...] = ()
    constraints: RequestConstraints = field(default_factory=RequestConstraints)
    required_output: RequiredOutput = field(default_factory=RequiredOutput)
    requester: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)


class RequestParser:
    """Build validated, in-memory request objects from plain text."""

    def parse(
        self,
        text: str,
        *,
        request_type: RequestType = "research",
        context: dict[str, Any] | None = None,
        requester: dict[str, Any] | None = None,
        permissions: dict[str, Any] | None = None,
        constraints: RequestConstraints | None = None,
        required_output: RequiredOutput | None = None,
    ) -> InformationRequest:
        """Normalize *text* and return a complete InformationRequest."""
        objective = " ".join(text.split())
        if not objective:
            raise ValidationError("An information request requires a non-empty objective.")

        return InformationRequest(
            request_id=ULID.new("REQ_"),
            request_type=request_type,
            objective=objective,
            question=objective if objective.endswith("?") else None,
            context=dict(context or {}),
            constraints=constraints or RequestConstraints(),
            required_output=required_output or RequiredOutput(),
            requester=dict(requester or {}),
            permissions=dict(permissions or {}),
        )
