"""§13.2/§14.4 — freshness of the delivered sources and source contradictions.

Two §21 tools existed and were never called on the sources a run delivers:

* ``check_freshness`` (§13.2, §41.5) — the ``freshness`` block of a source was
  never evaluated, so ``sources[].freshness`` stayed empty and the
  ``sources.freshness`` column was written as ``NULL``;
* ``compare_sources`` (§14.4) — the pipeline carried an empty ``conflicts`` slot,
  so a file and a web page disagreeing about the same measurement produced a
  delivery that looked unanimous.

This module is the missing link, with the same three rules as the dataset
quality one: the material comes from what the run already holds, an unknown
answer is stated (never guessed), and every issue becomes a limitation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.information_unit import InformationUnit
from app.domain.entities.source import Source
from app.tools.files.source_comparator import check_freshness, compare_sources

__all__ = ["SourceQualityReport", "assess_sources", "to_domain_source", "to_domain_unit"]

#: §14.4 claim shape the detector reads (``conflict_detector.group_by_subject_and_predicate``).
CLAIM_KEYS = ("subject", "predicate", "value")


def claim_projection(unit: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project a delivered unit onto the §14.4 claim shape, or return ``None``.

    The §14.4 detector compares units that declare ``subject``/``predicate``/
    ``value`` — and **nothing in the pipeline produced that triple**, so it could
    never fire on real material. Two mechanical projections fix that without
    inventing anything:

    * a unit already carrying the triple is used as-is (the §11 contract shape);
    * a **record** unit (``content["values"]``) is normalized wide-to-long: the
      row's descriptive values name the subject (``Paris`` — that is how a reader
      names the row), each numeric column becomes a predicate and its cell the
      value. That is what the row actually claims — *Paris, population =
      2 148 000* — not a guess.

    Anything else (a web sentence with no triple) is **not comparable**: the
    caller counts it and the delivery says so, rather than arbitrating silently.
    """
    content = unit.get("content")
    if not isinstance(content, Mapping):
        return None

    if all(key in content for key in CLAIM_KEYS):
        return {
            "subject": str(content["subject"]),
            "predicate": str(content["predicate"]),
            "value": content["value"],
        }

    values = content.get("values")
    if not isinstance(values, Mapping) or not values:
        return None

    descriptive = {
        str(key): value
        for key, value in values.items()
        if not isinstance(value, (int, float)) or isinstance(value, bool)
    }
    numeric = {
        str(key): value
        for key, value in values.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    if not numeric:
        return None
    subject = (
        "; ".join(str(value) for _, value in sorted(descriptive.items()))
        or str(unit.get("dataset_id") or unit.get("document_id") or "record")
    )
    # One claim per numeric column: a row can legitimately disagree about
    # several measures, and grouping them under one predicate would hide which
    # measure is contested.
    return {
        "subject": subject,
        "predicate": ",".join(sorted(numeric)),
        "value": numeric if len(numeric) > 1 else next(iter(numeric.values())),
    }


def to_domain_source(source: Mapping[str, Any]) -> Source:
    """Build the §27 ``Source`` entity from a delivered ``sources[]`` entry."""
    reliability = source.get("reliability_score")
    return Source(
        source_id=str(source.get("source_id") or source.get("id") or "SRC_UNKNOWN"),
        type=str(source.get("source_type") or source.get("type") or "web"),
        url=str(source.get("url") or ""),
        reliability_score=float(reliability) if reliability is not None else 0.5,
        freshness=dict(source.get("freshness") or {}),
    )


#: §11 types the ``InformationUnit`` entity accepts. The ingestion also names
#: rows ``table_row``: what §14.4 compares is the *claim*, so an unknown label is
#: mapped to ``text`` instead of being dropped.
_UNIT_TYPES = ("text", "number", "table", "record", "image_region", "document_fragment")


def to_domain_unit(unit: Mapping[str, Any]) -> InformationUnit | None:
    """Build an §11 ``InformationUnit`` from a delivered unit, or ``None``.

    A unit the entity cannot represent (unknown ``type``, unbounded payload) is
    skipped rather than forced: the comparison must never be fed a fabricated
    claim, and a skipped unit is reported by the caller.
    """
    raw_type = str(unit.get("type") or "text")
    payload = {
        "information_id": str(unit.get("information_id") or ""),
        "type": raw_type if raw_type in _UNIT_TYPES else "text",
        "content": dict(unit.get("content") or {}),
        "raw_reference": dict(unit.get("raw_reference") or {}),
        "source_id": str(unit.get("source_id") or ""),
        "document_id": unit.get("document_id"),
        "dataset_id": unit.get("dataset_id"),
        "location": dict(unit.get("location") or {}),
        "context": dict(unit.get("context") or {}),
        "language": unit.get("language"),
        "unit": unit.get("unit"),
        "time": dict(unit.get("time") or {}),
        "classification": dict(unit.get("classification") or {}),
        "quality": dict(unit.get("quality") or {}),
        "confidence": dict(unit.get("confidence") or {}),
        "provenance": dict(unit.get("provenance") or {}),
        "versions": list(unit.get("versions") or []),
        "data_stage": unit.get("data_stage") or "derived",
    }
    if not payload["information_id"] or not payload["source_id"]:
        return None
    try:
        return InformationUnit(**payload)
    except Exception:  # noqa: BLE001 - a unit the entity refuses is not a claim
        return None


class SourceQualityReport:
    """The §13.2 freshness of each source and the §14.4 conflicts between them."""

    def __init__(self) -> None:
        self.freshness: dict[str, dict[str, Any]] = {}
        self.conflicts: list[Any] = []
        self.limitations: list[str] = []
        self.assessed_sources = 0
        self.compared_units = 0
        self.incomparable_units = 0

    def to_dict(self) -> dict[str, Any]:
        """Return the delivery-level ``source_quality`` block."""
        return {
            "freshness": self.freshness,
            "conflicts": len(self.conflicts),
            "assessed_sources": self.assessed_sources,
            "compared_units": self.compared_units,
            "incomparable_units": self.incomparable_units,
            "not_a_probability": True,
        }


async def _assess_freshness(
    source: Mapping[str, Any], collected: SourceQualityReport
) -> None:
    """Evaluate the §13.2 freshness of one source and record the verdict."""
    domain = to_domain_source(source)
    try:
        result = await check_freshness(domain)
    except Exception as error:  # noqa: BLE001 - one source never breaks the colis
        collected.limitations.append(
            f"Fraîcheur §13.2 non évaluée pour {domain.source_id} "
            f"({type(error).__name__}: {error})."
        )
        return

    declared = dict(source.get("freshness") or {})
    block = {
        **declared,
        # The evaluation is stored with the declaration so the column carries an
        # answer a later run can reuse — and so a reader can tell "declared
        # fresh" from "checked and fresh" (§41.5).
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "score": float(result.score),
        "max_age_days": result.details.get("max_age_days"),
        "issues": list(result.issues),
    }
    collected.freshness[domain.source_id] = block
    collected.assessed_sources += 1
    source["freshness"] = block  # type: ignore[index]
    for issue in result.issues:
        collected.limitations.append(
            f"Fraîcheur §13.2 ({domain.source_id}) : {issue}"
        )


async def _assess_conflicts(
    sources: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
    collected: SourceQualityReport,
) -> None:
    """Run the §14.4 comparison over the claims the delivered units carry."""
    domain_sources = [to_domain_source(source) for source in sources]
    by_source: dict[str, list[InformationUnit]] = {}
    incomparable = 0
    for unit in units:
        claim = claim_projection(unit)
        if claim is None:
            incomparable += 1
            continue
        domain_unit = to_domain_unit({**unit, "content": claim})
        if domain_unit is None:
            incomparable += 1
            continue
        by_source.setdefault(domain_unit.source_id, []).append(domain_unit)

    collected.compared_units = sum(len(group) for group in by_source.values())
    collected.incomparable_units = incomparable

    distinct_sources = {str(source.source_id) for source in domain_sources}
    if len(distinct_sources) > 1 and incomparable:
        # §37 — the delivery must not look unanimous when part of the material
        # could not be compared at all: that would be a silent arbitration.
        collected.limitations.append(
            f"Comparaison §14.4 partielle : {incomparable} unité(s) livrée(s) ne portent pas "
            "de triplet (subject, predicate, value) et n'ont donc pas pu être croisées."
        )
    if len(distinct_sources) < 2:
        return
    try:
        collected.conflicts = list(await compare_sources(domain_sources, by_source))
    except Exception as error:  # noqa: BLE001 - an unreadable comparison is stated
        collected.limitations.append(
            f"Comparaison §14.4 non exécutée ({type(error).__name__}: {error}) : "
            "les sources livrées n'ont pas été croisées."
        )


async def assess_sources(
    sources: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
) -> SourceQualityReport:
    """Evaluate the freshness of *sources* and compare what they claim (§13/§14.4).

    Args:
        sources: The ``sources[]`` of the colis, mutated in place: each entry
            gains the evaluated ``freshness`` block (persisted by the pipeline).
        units: The delivered §11 units, grouped by ``source_id`` for the
            comparison. A source that delivered no unit is still assessed for
            freshness — its silence is not a contradiction.

    Returns:
        The report: freshness per source, the conflicts the §14.4 detector
        found, and the limitations the delivery must repeat.
    """
    collected = SourceQualityReport()
    for source in sources:
        await _assess_freshness(source, collected)
    await _assess_conflicts(sources, units, collected)
    return collected
