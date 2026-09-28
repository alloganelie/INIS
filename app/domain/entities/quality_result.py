"""Quality result returned by the §21 ``check_*`` tools and §13 checks."""

from pydantic import BaseModel, Field


class QualityResult(BaseModel):
    """Bounded quality score with its explicable details and issues (§13.2)."""

    score: float = Field(ge=0.0, le=1.0)
    details: dict = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Return whether the check reported no issue at all."""
        return not self.issues

    @classmethod
    def from_mapping(cls, mapping: dict) -> "QualityResult":
        """Build a result from the ``{"score", "details", "issues"}`` shape.

        The §13 check implementations return that plain mapping; this adapter
        keeps one canonical object for callers of the §21 tools.
        """
        return cls(
            score=float(mapping.get("score", 0.0)),
            details=dict(mapping.get("details") or {}),
            issues=list(mapping.get("issues") or []),
        )
