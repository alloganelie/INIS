"""Parse a free-text request into the INIS section 7 request contract.

The §7 value objects (``RequestConstraints``, ``RequiredOutput``,
``RequestType``) live in :mod:`app.domain.value_objects.request_constraints`
and are re-exported here for backward compatibility.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.errors import ValidationError
from app.domain.value_objects.request_constraints import RequestConstraints
from app.domain.value_objects.request_constraints import RequestType
from app.domain.value_objects.request_constraints import RequiredOutput
from app.domain.value_objects.ulid import ULID

__all__ = [
    "InformationRequest",
    "RequestConstraints",
    "RequestParser",
    "RequestType",
    "RequiredOutput",
]


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
