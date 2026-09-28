"""Source suspicion module per INIS §41.7 (désinformation / manipulation)."""

from app.domain.entities.source import SourceSuspicion
from app.quality.suspicion.assessor import SUSPICION_WARNING_KEY
from app.quality.suspicion.assessor import apply_suspicion_warning
from app.quality.suspicion.assessor import assess_source_suspicion
from app.quality.suspicion.assessor import verify_finding_warning
from app.quality.suspicion.bias_assessor import assess_editorial_bias
from app.quality.suspicion.bias_assessor import lexical_one_sidedness
from app.quality.suspicion.freshness_detector import detect_freshness_manipulation
from app.quality.suspicion.mirror_detector import content_fingerprint
from app.quality.suspicion.mirror_detector import detect_mirror
from app.quality.suspicion.mirror_detector import similarity
from app.quality.suspicion.synthetic_detector import detect_synthetic_content

__all__ = [
    "SourceSuspicion",
    "SUSPICION_WARNING_KEY",
    "apply_suspicion_warning",
    "assess_editorial_bias",
    "assess_source_suspicion",
    "content_fingerprint",
    "detect_freshness_manipulation",
    "detect_mirror",
    "detect_synthetic_content",
    "lexical_one_sidedness",
    "similarity",
    "verify_finding_warning",
]