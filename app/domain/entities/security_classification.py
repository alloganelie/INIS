"""Domain entity for PII and resource sensitivity classification."""

from typing import Literal

from pydantic import BaseModel, Field


class SecurityClassification(BaseModel):
    """Sensitivity and PII metadata required by INIS section 19.4."""

    sensitivity: Literal["low", "medium", "high", "critical"]
    pii: bool
    categories: list[str] = Field(default_factory=list)
