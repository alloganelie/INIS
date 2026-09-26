"""Request execution constraints and required output (§7).

Single source of truth shared by the understanding agent
(:class:`~app.agents.understanding.request_parser.RequestParser`) and the API
wire schemas (:mod:`app.api.v1.requests.schemas`). Keeping the defaults here
means the API contract and the domain contract cannot drift apart.
"""

from dataclasses import dataclass
from typing import Any
from typing import Literal

__all__ = [
    "DEFAULT_CONSTRAINTS",
    "DEFAULT_REQUIRED_OUTPUT",
    "OutputFormat",
    "RequestConstraints",
    "RequestType",
    "RequiredOutput",
]

#: The five request types of §7.
RequestType = Literal["research", "source", "evidence", "data", "artifact"]

#: The six delivery formats of §24.
OutputFormat = Literal["evidence_package", "json", "csv", "xlsx", "pdf", "xml"]


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

    format: OutputFormat = "evidence_package"
    fields: tuple[str, ...] = ()


#: Canonical default instances (used by API wire schemas as their defaults).
DEFAULT_CONSTRAINTS = RequestConstraints()
DEFAULT_REQUIRED_OUTPUT = RequiredOutput()
