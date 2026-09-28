"""Composer of the §41.7 ``source_suspicion`` ``[CONFIG]`` signal.

Brings the four detectors together (synthetic content, mirrors, editorial
bias, freshness manipulation) into a single :class:`SourceSuspicion`, and
provides the enforcement helpers for the §41.7 hard rule:

    une source avec ``synthetic_content_detected = true`` NE DOIT PAS
    contribuer à un ``Finding`` sans avertissement explicite.
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.domain.entities.source import SourceSuspicion
from app.quality.suspicion.bias_assessor import assess_editorial_bias
from app.quality.suspicion.bias_assessor import lexical_one_sidedness
from app.quality.suspicion.freshness_detector import detect_freshness_manipulation
from app.quality.suspicion.mirror_detector import detect_mirror
from app.quality.suspicion.synthetic_detector import detect_synthetic_content

#: Key under which the explicit warning travels on a ``Finding`` dict.
SUSPICION_WARNING_KEY = "suspicion_warning"


def assess_source_suspicion(
    texts: Sequence[str] = (),
    *,
    metadata: Mapping[str, Any] | None = None,
    known_sources: Sequence[tuple[str, str]] = (),
    contradicted_claims: int = 0,
    total_claims: int | None = None,
    stated_published_at: datetime | None = None,
    content_date: datetime | None = None,
    now: datetime | None = None,
) -> SourceSuspicion:
    """Build the full §41.7 signal for one source.

    Args:
        texts: recent contents attributed to the source under examination.
        metadata: source metadata (``generator`` flags synthetic content).
        known_sources: ``(source_id, text)`` pairs of other sources, used to
            detect that this source mirrors one of them.
        contradicted_claims: claims of this source contradicted elsewhere.
        total_claims: denominator for the contradiction rate.
        stated_published_at: publish date claimed by the source.
        content_date: real date of the underlying content.
        now: reference instant for freshness checks.
    """
    reasons: list[str] = []

    synthetic, reason = detect_synthetic_content(
        "\n".join(texts), metadata=metadata
    )
    if synthetic and reason:
        reasons.append(reason)

    mirror_of: str | None = None
    if texts and known_sources:
        mirror_of = detect_mirror(texts[0], known_sources)
        if mirror_of is not None:
            reasons.append(f"content mirrors {mirror_of}")

    bias_score = assess_editorial_bias(
        texts,
        contradicted_claims=contradicted_claims,
        total_claims=total_claims,
    )
    if bias_score >= 0.5:
        one_sidedness = lexical_one_sidedness(texts)
        reasons.append(
            f"editorial bias score {bias_score:.2f} "
            f"(one-sidedness {one_sidedness:.2f}, "
            f"{contradicted_claims} contradicted claims)"
        )

    freshness_suspected, reason = detect_freshness_manipulation(
        stated_published_at, content_date, now=now
    )
    if freshness_suspected and reason:
        reasons.append(reason)

    return SourceSuspicion(
        synthetic_content_detected=synthetic,
        mirror_of=mirror_of,
        editorial_bias_score=bias_score,
        freshness_manipulation_suspected=freshness_suspected,
        suspicion_reason="; ".join(reasons) if reasons else None,
    )


def apply_suspicion_warning(
    finding: Mapping[str, Any],
    suspicion: SourceSuspicion,
) -> dict[str, Any]:
    """Return a copy of *finding* carrying the explicit §41.7 warning.

    The warning is added whenever the source requires it (synthetic
    content), making the finding compliant with the hard rule; the original
    mapping is never mutated.
    """
    result = dict(finding)
    if suspicion.requires_finding_warning and SUSPICION_WARNING_KEY not in result:
        result[SUSPICION_WARNING_KEY] = (
            suspicion.suspicion_reason or "synthetic content detected (§41.7)"
        )
    return result


def verify_finding_warning(
    finding: Mapping[str, Any],
    suspicion: SourceSuspicion,
) -> None:
    """Enforce the §41.7 hard rule on a finding about to be delivered.

    Raises:
        ValueError: when a synthetic-sourced finding carries no explicit
            warning.
    """
    if suspicion.requires_finding_warning and not finding.get(SUSPICION_WARNING_KEY):
        raise ValueError(
            "finding from a synthetic source (§41.7) must carry an explicit "
            f"'{SUSPICION_WARNING_KEY}' before delivery"
        )
