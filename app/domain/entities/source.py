"""Domain entity representing an information source."""

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A source that provides provenance for factual information."""

    source_id: str
    type: str
    url: str
    reliability_score: float = Field(ge=0.0, le=1.0)
    freshness: dict
