"""Domain entity representing a source discovered during planning."""

from pydantic import BaseModel, Field


class SourceCandidate(BaseModel):
    """A ranked, not-yet-selected source candidate."""

    url: str
    provider: str
    score: float = Field(ge=0.0, le=1.0)
