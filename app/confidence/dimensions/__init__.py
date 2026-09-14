"""The 7 confidence dimensions (§15.1).

Submodules are imported so ``dimensions.<module>.compute(...)`` works
after ``from app.confidence import dimensions``; each submodule
exposes a single pure ``compute`` function.
"""

from app.confidence.dimensions import cross_source_agreement
from app.confidence.dimensions import data_quality_signal
from app.confidence.dimensions import evidence_strength
from app.confidence.dimensions import extraction_confidence
from app.confidence.dimensions import methodological_consistency
from app.confidence.dimensions import source_freshness
from app.confidence.dimensions import source_reliability

__all__ = [
    "source_reliability",
    "source_freshness",
    "extraction_confidence",
    "data_quality_signal",
    "evidence_strength",
    "cross_source_agreement",
    "methodological_consistency",
]
