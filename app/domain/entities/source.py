"""Domain entity representing an information source."""

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects.ulid import ULID


class Source(BaseModel):
    """A source that provides provenance for factual information."""

    source_id: str
    type: str
    url: str
    reliability_score: float = Field(ge=0.0, le=1.0)
    freshness: dict


class SourceSuspicion(BaseModel):
    """Source suspicion signal of §41.7 (``[CONFIG]`` block).

    A source carrying any suspicion flag MUST be surfaced explicitly: a
    source with ``synthetic_content_detected = true`` MUST NOT contribute to
    a ``Finding`` without an explicit warning (§41.7).
    """

    synthetic_content_detected: bool = False
    mirror_of: str | None = None
    editorial_bias_score: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness_manipulation_suspected: bool = False
    suspicion_reason: str | None = None

    @field_validator("mirror_of")
    @classmethod
    def _validate_mirror_of(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("SRC_") or not ULID.is_valid(value):
            raise ValueError("mirror_of must be a SRC_{ULID} identifier (§0.3)")
        return value

    @property
    def requires_finding_warning(self) -> bool:
        """Whether findings fed by this source must carry an explicit warning."""
        return self.synthetic_content_detected

    @property
    def is_suspicious(self) -> bool:
        """Whether any §41.7 signal is raised."""
        return bool(
            self.synthetic_content_detected
            or self.mirror_of is not None
            or self.freshness_manipulation_suspected
            or self.editorial_bias_score >= 0.5
        )

    def to_dict(self) -> dict:
        """Return the exact §41.7 ``source_suspicion`` ``[CONFIG]`` projection."""
        return {
            "synthetic_content_detected": self.synthetic_content_detected,
            "mirror_of": self.mirror_of,
            "editorial_bias_score": self.editorial_bias_score,
            "freshness_manipulation_suspected": self.freshness_manipulation_suspected,
            "suspicion_reason": self.suspicion_reason,
        }
