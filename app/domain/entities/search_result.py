"""Domain entity representing one result returned by a search provider."""

from pydantic import BaseModel, Field

from app.domain.entities.source_candidate import SourceCandidate


class SearchResult(BaseModel):
    """A scored result from the SearchProvider interface defined in section 10.1."""

    title: str
    url: str
    snippet: str | None = None
    score: float = Field(..., ge=0.0, le=1.0)
    provider: str
    source_candidate: SourceCandidate | None = None
