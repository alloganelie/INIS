"""Domain entity representing evidence for an information-backed claim."""

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A source excerpt that supports or contradicts a claim."""

    evidence_id: str
    claim_id: str | None
    information_id: str
    document_id: str
    source_id: str
    excerpt: str
    location: dict
    strength: float = Field(ge=0.0, le=1.0)
