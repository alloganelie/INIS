"""Domain representation of a delivered InformationPackage."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.errors import ValidationError


class InformationPackage(BaseModel):
    """A traceable collection of information units for one request."""

    package_id: str
    request_id: str
    units: list[dict]
    confidence: dict
    provenance: dict
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_stage: Literal["raw", "normalized", "enriched", "derived"]

    def validate(self) -> None:
        """Enforce the requirement that factual output has provenance."""
        if not self.provenance:
            raise ValidationError("InformationPackage requires provenance.")
