"""Domain values returned by the §17 memory lookup.

``memory_lookup`` answers one question with a :class:`MemoryResult`: either the
already-acquired information is sufficient, or it is not and the caller must
search again. A candidate carries everything the §17.1 filter chain inspects —
completeness of provenance, source freshness, and the §18.2/§41.5 reuse policy —
so the decision never has to reach back into storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["MemoryCandidate", "MemoryResult"]


@dataclass(frozen=True)
class MemoryCandidate:
    """One previously acquired unit proposed for reuse (§17.1)."""

    information_id: str
    content: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    data_stage: str = "normalized"
    #: When the source was last observed to be current, if known.
    source_freshness: datetime | None = None
    #: ``False`` when the §41.5/§18.2 policy forbids reusing this record.
    policy_allows_reuse: bool = True
    #: ``True`` once the record was soft-deleted (§18.2): never reusable.
    deleted: bool = False

    @property
    def provenance_complete(self) -> bool:
        """Return whether the unit documents where it came from (§0.2, §11)."""
        if not self.provenance:
            return False
        return bool(
            self.provenance.get("source_id")
            or self.provenance.get("extracted_from")
            or self.provenance.get("url")
        )


@dataclass(frozen=True)
class MemoryResult:
    """The §17.1 outcome of a memory lookup."""

    #: ``True`` when at least one candidate passed every filter.
    sufficient: bool
    #: The candidate that may be reused (empty when ``sufficient`` is False).
    items: tuple[MemoryCandidate, ...] = ()
    #: Why nothing could be reused — never empty when ``sufficient`` is False.
    reason: str | None = None
    #: The question the lookup answered.
    question: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection used by the delivery payload."""
        return {
            "sufficient": self.sufficient,
            "question": self.question,
            "reason": self.reason,
            "information_ids": [item.information_id for item in self.items],
        }
