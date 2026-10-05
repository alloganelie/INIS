"""Domain entity representing a data transformation (§12.1).

Every RAW → NORMALIZED → ENRICHED → DERIVED step is recorded as a
``Transformation`` so the lineage of a delivered value can always be replayed
back to its inputs (§0.2, §12, §12.1). The shape mirrors the ``transformations``
table created by revision ``0004`` and the JSON contract of §12.1.

Two rules are enforced here rather than left to the caller:

* ``transformation_id`` is a ``TRF_{ULID}`` identifier (§0.3);
* a ``failure`` must carry a ``justification`` — §25.1 requires an explicit
  reason for every failure, and an unexplained failed transformation would be
  an unauditable dead end in the lineage graph.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.errors import ValidationError
from app.core.time import utc_now
from app.domain.value_objects.ulid import ULID

__all__ = ["TRANSFORMATION_RESULTS", "Transformation"]

#: The §12.1 allowed outcomes.
TRANSFORMATION_RESULTS: tuple[str, ...] = ("success", "failure")


class Transformation(BaseModel):
    """One recorded RAW → DERIVED operation (§12.1)."""

    transformation_id: str
    input_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    operator: str | None = None
    tool: str | None = None
    tool_version: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
    result: Literal["success", "failure"] = "success"
    justification: str | None = None

    @field_validator("transformation_id")
    @classmethod
    def _validate_transformation_id(cls, value: str) -> str:
        """Require the canonical ``TRF_{ULID}`` identifier (§0.3)."""
        if not value.startswith("TRF_") or not ULID.is_valid(value):
            raise ValueError("transformation_id must be a valid TRF_ ULID")
        return value

    def validate(self) -> None:
        """Enforce the §12.1/§25.1 invariants of a recorded transformation.

        Raises:
            ValidationError: when a successful transformation claims no output,
                or when a failure does not state why it failed.
        """
        if self.result == "success" and not self.output_ids:
            raise ValidationError(
                "a successful Transformation must declare at least one output_id."
            )
        if self.result == "failure" and not (self.justification or "").strip():
            raise ValidationError(
                "a failed Transformation must carry an explicit justification (§25.1)."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the exact §12.1 JSON projection."""
        return {
            "transformation_id": self.transformation_id,
            "input_ids": list(self.input_ids),
            "output_ids": list(self.output_ids),
            "operator": self.operator,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "parameters": dict(self.parameters),
            "timestamp": self.timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "result": self.result,
            "justification": self.justification,
        }
