"""Derive the 7 §15.1 dimension inputs from collected delivery signals.

The dimension calculators (``app/confidence/dimensions/*``) each own one pure
formula, and :func:`app.confidence.confidence_scorer.score` owns the §15.2
weighted sum. What was missing is the bridge between the two and the material a
run actually collected: the pipeline used to pass a hardcoded dict of seven
constants, so the delivered confidence was the same for every request —
including the ones that found nothing at all. This module is that bridge.

Everything here is a *derivation*, never an invention:

* a source that carries no ``reliability_score`` is excluded from the
  reliability mean instead of being credited with a made-up score;
* a dimension with no usable signal falls back to the neutral 0.5 documented by
  the calculators themselves (``compute({})``), or to 0.0 when the calculator
  defines emptiness as absence of corroboration;
* signals are returned next to the values so the delivery can state *why* a
  dimension scored what it scored (§15.3 explainability).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from app.confidence.dimensions import cross_source_agreement
from app.confidence.dimensions import data_quality_signal
from app.confidence.dimensions import evidence_strength
from app.confidence.dimensions import extraction_confidence
from app.confidence.dimensions import methodological_consistency
from app.confidence.dimensions import source_freshness
from app.confidence.dimensions import source_reliability

__all__ = ["derive"]

#: §15.1 dimension keys, in ``DIMENSION_ORDER``.
_DIMENSION_KEYS = (
    "source_reliability",
    "source_freshness",
    "extraction_confidence",
    "data_quality",
    "evidence_strength",
    "cross_source_agreement",
    "methodological_consistency",
)


def _score_of(value: Any) -> float | None:
    """Return *value* as a 0..1 float, or ``None`` when it carries no score.

    Accepts a plain number, a §11 ``{"score": x}`` block or any mapping naming
    one of the documented score keys.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, Mapping):
        for key in ("score", "confidence_score", "quality_score", "strength"):
            if key in value:
                return _score_of(value[key])
    return None


def _mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of *values*, neutral 0.5 when empty."""
    return sum(values) / len(values) if values else 0.5


def _unit_text(unit: Mapping[str, Any]) -> str:
    """Return the comparable text of one information unit (§11 ``content``)."""
    content = unit.get("content")
    if isinstance(content, Mapping):
        for key in ("text", "value", "summary"):
            raw = content.get(key)
            if isinstance(raw, str) and raw.strip():
                return " ".join(raw.lower().split())
    return ""


def _has_provenance(unit: Mapping[str, Any]) -> bool:
    """Return ``True`` when the unit documents where it came from (§0.2)."""
    provenance = unit.get("provenance")
    if not isinstance(provenance, Mapping):
        return False
    return bool(provenance.get("extracted_from") or provenance.get("url"))


def derive(
    *,
    sources: Sequence[Mapping[str, Any]] = (),
    units: Sequence[Mapping[str, Any]] = (),
    findings: Sequence[Any] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the §15.1 dimensions of a delivery plus the signals behind them.

    Args:
        sources: Delivered sources (``SRC_`` entries of the §24.1 payload).
        units: Delivered §11 information units.
        findings: Verified findings kept for delivery — the §24.1 shape carries
            ``confidence`` per finding.
        evidence: Delivered §14.2 evidence records (``strength``).
        now: Reference instant for freshness (defaults to *now*, UTC).

    Returns:
        ``{"dimensions": {7 keys}, "signals": {...}}`` — ``dimensions`` drops
        straight into :func:`app.confidence.confidence_scorer.score`.
    """
    # -- source_reliability / source_freshness ---------------------------
    # An internal ``internal://`` source has no measurable reliability: it is
    # left out of the mean rather than credited with a default score.
    measurable_sources = [
        source
        for source in sources
        if isinstance(source, Mapping) and _score_of(source.get("reliability_score")) is not None
    ]
    reliability = _mean([source_reliability.compute(source) for source in measurable_sources])
    freshness = _mean([source_freshness.compute(source, now) for source in measurable_sources])

    # -- extraction_confidence -------------------------------------------
    extraction_values: list[float] = []
    for item in findings:
        if not isinstance(item, Mapping):
            continue
        value = _score_of(item.get("extraction_confidence"))
        if value is None:
            value = _score_of(item.get("confidence"))
        extraction_values.append(
            extraction_confidence.compute(
                {"extraction_confidence": value} if value is not None else {}
            )
        )
    extraction = _mean(extraction_values)

    # -- data_quality ----------------------------------------------------
    # §13 runs no check inside the pipeline before delivery: the neutral signal
    # of the calculator is reported, and it rises as soon as units carry the
    # ``quality`` block produced by the quality zone.
    quality_values = [
        value
        for unit in units
        if isinstance(unit, Mapping)
        for value in [_score_of(unit.get("quality"))]
        if value is not None
    ]
    data_quality = data_quality_signal.compute(
        {"quality_score": _mean(quality_values)} if quality_values else {}
    )

    # -- evidence_strength ------------------------------------------------
    evidence_values: list[float] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        value = _score_of(item.get("strength"))
        evidence_values.append(
            evidence_strength.compute({"strength": value} if value is not None else {})
        )
    strength = _mean(evidence_values)

    # -- cross_source_agreement -------------------------------------------
    # Agreement is only observable once two distinct sources were consulted:
    # each unit whose text is corroborated by another source scores 1.0, the
    # others 0.0. With a single source the dimension is not testable → neutral.
    distinct_sources = {
        str(unit.get("source_id"))
        for unit in units
        if isinstance(unit, Mapping) and unit.get("source_id")
    }
    grouped: dict[str, set[str]] = {}
    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        text = _unit_text(unit)
        if text:
            grouped.setdefault(text, set()).add(str(unit.get("source_id") or ""))
    corroborated = sum(1 for owners in grouped.values() if len(owners) > 1)
    agreement_signals = (
        [{"agreement": 1.0 if len(owners) > 1 else 0.0} for owners in grouped.values()]
        if len(distinct_sources) >= 2
        else []
    )
    agreement = (
        cross_source_agreement.compute(agreement_signals) if agreement_signals else 0.5
    )

    # -- methodological_consistency ---------------------------------------
    # One method is applied consistently when every unit documents the method
    # and the origin it was extracted from (§11 ``provenance``).
    consistency_signals = [
        {"consistency": 1.0 if _has_provenance(unit) else 0.0}
        for unit in units
        if isinstance(unit, Mapping)
    ]
    consistency = methodological_consistency.compute(consistency_signals)

    dimensions = dict(
        zip(
            _DIMENSION_KEYS,
            (
                reliability,
                freshness,
                extraction,
                data_quality,
                strength,
                agreement,
                consistency,
            ),
            strict=True,
        )
    )
    signals = {
        "sources_measured": len(measurable_sources),
        "findings_measured": len(extraction_values),
        "units_measured": len(consistency_signals),
        "evidence_measured": len(evidence_values),
        "distinct_sources": len(distinct_sources),
        "corroborated_units": corroborated,
    }
    return {"dimensions": dimensions, "signals": signals}
