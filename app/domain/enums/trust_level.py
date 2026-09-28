"""Inter-agent trust levels (§41.10)."""

from enum import Enum


class TrustLevel(str, Enum):
    """``full | partial | minimal`` — delegation confidence between agents."""

    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"
