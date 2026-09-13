"""Domain entity representing a fact or explicitly qualified assertion."""

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """An assertion linked to information units and evidence."""

    claim_id: str
    statement: str
    information_ids: list[str]
    evidence_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    epistemic_status: Literal["fact", "hypothesis", "assumption", "uncertainty"]
