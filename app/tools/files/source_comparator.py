"""``check_freshness`` and ``compare_sources`` internal tools per §21.

Both operate on :class:`~app.domain.entities.source.Source` values:

* :func:`check_freshness` scores the freshness declaration the source carries
  (§9.2). A source with no freshness metadata is reported as *stale with an
  explicit reason* rather than being assumed fresh (§0.2, §25.1).
* :func:`compare_sources` reports contradictions between sources. When the
  caller supplies the information units extracted from each source, the §14.4
  conflict detector does the work; without units, only contradictions that are
  *readable from the source records themselves* (same location declared with
  diverging reliability or freshness) are reported.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.entities.conflict import Conflict
from app.domain.entities.information_unit import InformationUnit
from app.domain.entities.quality_result import QualityResult
from app.domain.entities.source import Source
from app.domain.value_objects.ulid import ULID
from app.quality.checks import FreshnessCheck
from app.quality.conflict.conflict_detector import detect_conflicts

__all__ = ["check_freshness", "compare_sources"]

#: Freshness keys read from ``Source.freshness``, in priority order.
_TIMESTAMP_KEYS = ("updated_at", "last_checked_at", "checked_at", "retrieved_at")
_MAX_AGE_KEYS = ("max_age_days", "ttl_days")


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning ``None`` when it is unusable."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def check_freshness(source: Source) -> QualityResult:
    """Score the freshness of *source* against its declared maximum age (§21).

    Args:
        source: The source whose ``freshness`` block is evaluated.

    Returns:
        A :class:`QualityResult`. When the source declares neither a usable
        timestamp nor a declared age, the score is ``0.0`` and the issue names
        the missing metadata, so "unknown" can never be mistaken for "fresh".
    """
    freshness = dict(source.freshness or {})

    max_age_days = 30
    for key in _MAX_AGE_KEYS:
        value = freshness.get(key)
        if isinstance(value, (int, float)) and value > 0:
            max_age_days = int(value)
            break

    timestamp: datetime | None = None
    used_key: str | None = None
    for key in _TIMESTAMP_KEYS:
        timestamp = _parse_timestamp(freshness.get(key))
        if timestamp is not None:
            used_key = key
            break

    if timestamp is None:
        declared_age = freshness.get("age_days")
        if isinstance(declared_age, (int, float)):
            score = 1.0 if float(declared_age) <= max_age_days else 0.0
            return QualityResult.from_mapping(
                {
                    "score": score,
                    "details": {
                        "source_id": source.source_id,
                        "timestamp_key": "age_days",
                        "age_days": float(declared_age),
                        "max_age_days": max_age_days,
                    },
                    "issues": [] if score == 1.0 else ["data is stale"],
                }
            )
        return QualityResult.from_mapping(
            {
                "score": 0.0,
                "details": {"freshness": freshness, "source_id": source.source_id},
                "issues": [
                    "no usable freshness timestamp "
                    f"(expected one of {', '.join(_TIMESTAMP_KEYS)})"
                ],
            }
        )

    # ``FreshnessCheck`` reads ``updated_at``; this tool accepts five key names
    # (§9.2 declarations vary by connector). Without the normalization below, a
    # source that declared ``retrieved_at`` — what the file ingestion writes —
    # was scored 0.0 as if it had declared nothing: the timestamp was found and
    # then dropped.
    evaluation = await FreshnessCheck(max_age_days=max_age_days).run(
        {**freshness, "updated_at": timestamp.isoformat()}
    )
    details = dict(evaluation["details"])
    details.update(
        {
            "source_id": source.source_id,
            "timestamp_key": used_key,
            "max_age_days": max_age_days,
        }
    )
    return QualityResult.from_mapping(
        {"score": evaluation["score"], "details": details, "issues": evaluation["issues"]}
    )


def _source_conflicts(sources: list[Source]) -> list[Conflict]:
    """Report sources declaring diverging reliability or freshness for one location."""
    by_location: dict[str, list[Source]] = {}
    for source in sources:
        by_location.setdefault(source.url, []).append(source)

    conflicts: list[Conflict] = []
    for location, group in sorted(by_location.items()):
        if len(group) < 2:
            continue
        reliabilities = {round(float(source.reliability_score), 6) for source in group}
        freshness_keys = {
            repr(
                sorted(
                    (str(key), repr(value))
                    for key, value in (source.freshness or {}).items()
                )
            )
            for source in group
        }
        if len(reliabilities) < 2 and len(freshness_keys) < 2:
            continue
        ordered = sorted(group, key=lambda source: source.source_id)
        conflicts.append(
            Conflict(
                conflict_id=ULID.new("CONFLICT_"),
                information_a=ordered[0].source_id,
                information_b=ordered[1].source_id,
                difference_type="source_record",
                severity="medium" if len(reliabilities) > 1 else "low",
                resolution_status="open",
                resolution_evidence=[f"location:{location}"],
            )
        )
    return conflicts


async def compare_sources(
    sources: list[Source],
    units_by_source: dict[str, list[InformationUnit]] | None = None,
) -> list[Conflict]:
    """Detect contradictions between *sources* (§21, §14.4).

    Args:
        sources: The sources to cross-check.
        units_by_source: Information units extracted from each source, keyed by
            ``source_id``. When supplied, the §14.4 detector compares the actual
            claims the sources carry.

    Returns:
        The detected conflicts, in a deterministic order. INIS never invents a
        contradiction: an empty list means the supplied material agreed, or
        carried nothing comparable.
    """
    if units_by_source:
        units = [
            unit
            for source in sources
            for unit in (units_by_source.get(source.source_id) or [])
        ]
        return await detect_conflicts(units)
    return _source_conflicts(sources)
