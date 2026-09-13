"""Conflict entity types per INIS §14.3."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal


@dataclass
class Conflict:
    """Conflict entity per §14.3."""

    conflict_id: str
    information_a: str
    information_b: str
    difference_type: Literal["value", "definition", "date", "methodology", "scope"]
    severity: Literal["low", "medium", "high"]
    resolution_status: Literal["open", "investigated", "unresolved", "resolved"]
    resolution_evidence: list[str]
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
