"""Memory reuse per §17.1 — decide whether a question is already answered.

The specification defines the algorithm as a filter chain over the candidates a
search returns::

    candidates = await hybrid_search(question, filters=requirements.filters)
    for candidate in candidates:
        if not candidate.provenance_complete:   continue
        if not freshness_acceptable(candidate, requirements): continue
        if not policy_allows_reuse(candidate):  continue
        return MemoryResult(sufficient=True, items=[candidate])
    return MemoryResult(sufficient=False)

What matters for INIS is the *decision*, not where the candidates came from: the
same three filters have to hold whether the search is the §16 hybrid search over
persisted units or the §41.5 L1 cache the pipeline consults. The search is
therefore an injected callable (:data:`MemorySearch`) rather than a hard import,
which keeps this module free of storage dependencies and lets the reuse policy
be tested on its own.

Two filters are shared with the §41.5 cache policy and both are strict on
purpose:

* an unknown ``source_freshness`` is **not** acceptable when a threshold is
  configured — an entry of unknown age must not be reused;
* a soft-deleted record (§18.2) is never reused, whatever the policy says.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.entities.memory_result import MemoryCandidate, MemoryResult

__all__ = [
    "DEFAULT_FRESHNESS_THRESHOLD_HOURS",
    "EarlyStopDecision",
    "MemoryRequirements",
    "MemorySearch",
    "early_stop_decision",
    "freshness_acceptable",
    "memory_lookup",
    "policy_allows_reuse",
]

#: §41.5 ``freshness_threshold_hours`` default, reused as the §17 default.
DEFAULT_FRESHNESS_THRESHOLD_HOURS = 24

#: §17.1 filters a candidate had to pass to be reused. Named here so the decision
#: can state *which* criteria carried it instead of asserting "it is sufficient".
SUFFICIENCY_CRITERIA = ("provenance_complete", "freshness_acceptable", "policy_allows_reuse")

#: §16.2 mode a lookup must have run in to conclude sufficiency (see below).
SUFFICIENT_MODE = "hybrid"


@dataclass(frozen=True)
class MemoryRequirements:
    """The §17.1 ``requirements`` a lookup is evaluated against."""

    #: Oldest acceptable ``source_freshness``; ``0`` disables the check.
    freshness_threshold_hours: int = DEFAULT_FRESHNESS_THRESHOLD_HOURS
    #: Passed through to the search implementation (§17.1 ``filters``).
    filters: Mapping[str, Any] = field(default_factory=dict)

    def freshness_cutoff(self, now: datetime | None = None) -> datetime:
        """Return the oldest acceptable ``source_freshness`` instant."""
        return (now or datetime.now(UTC)) - timedelta(
            hours=self.freshness_threshold_hours
        )


#: A §16 hybrid search / §41.5 cache read, injected (§17.1 ``hybrid_search``).
MemorySearch = Callable[[str, MemoryRequirements], Awaitable[Sequence[MemoryCandidate]]]


def freshness_acceptable(
    candidate: MemoryCandidate,
    requirements: MemoryRequirements,
    now: datetime | None = None,
) -> bool:
    """Return whether *candidate* is recent enough to reuse (§17.1)."""
    if requirements.freshness_threshold_hours <= 0:
        return True
    if candidate.source_freshness is None:
        return False
    freshness = candidate.source_freshness
    if freshness.tzinfo is None:
        freshness = freshness.replace(tzinfo=UTC)
    return freshness >= requirements.freshness_cutoff(now)


def policy_allows_reuse(candidate: MemoryCandidate) -> bool:
    """Return whether policy permits reusing *candidate* (§17.1, §18.2)."""
    if candidate.deleted:
        return False
    return bool(candidate.policy_allows_reuse)


async def memory_lookup(
    question: str,
    requirements: MemoryRequirements | None = None,
    *,
    search: MemorySearch,
) -> MemoryResult:
    """Return the first reusable answer to *question*, or ``sufficient=False``.

    Args:
        question: The question the memory should already answer.
        requirements: §17.1 requirements; defaults to a 24-hour freshness
            threshold with no extra filters.
        search: The candidate provider (hybrid search over persisted units, the
            §41.5 L1 cache, …). Injected so the filter chain is testable and the
            module keeps no storage dependency.

    Returns:
        ``MemoryResult(sufficient=True, items=(candidate,))`` for the first
        candidate passing all three filters, else a ``MemoryResult`` whose
        ``reason`` names the filters that rejected every candidate.
    """
    if not question or not isinstance(question, str):
        raise ValueError("question must be a non-empty string")
    effective = requirements or MemoryRequirements()
    candidates = await search(question, effective)
    rejected: list[str] = []
    for candidate in candidates:
        if not candidate.provenance_complete:
            rejected.append(f"{candidate.information_id}: provenance incomplete")
            continue
        if not freshness_acceptable(candidate, effective):
            rejected.append(f"{candidate.information_id}: stale")
            continue
        if not policy_allows_reuse(candidate):
            rejected.append(f"{candidate.information_id}: reuse forbidden by policy")
            continue
        return MemoryResult(
            sufficient=True,
            items=(candidate,),
            reason=None,
            question=question,
        )
    if not candidates:
        reason = "no candidate found"
    else:
        reason = "; ".join(rejected) or "no reusable candidate"
    return MemoryResult(sufficient=False, items=(), reason=reason, question=question)


@dataclass(frozen=True)
class EarlyStopDecision:
    """The §17.1 early-stop decision: what was concluded and why (§8.4)."""

    #: ``True`` when the memory holds a reusable answer (the §17.1 algorithm).
    sufficient: bool
    #: ``True`` only when the run may **stop acquiring** on that basis.
    stopped_acquisition: bool
    #: The §17.1 filters the reused candidate passed.
    criteria: tuple[str, ...] = ()
    #: Why the acquisition was *not* stopped although the memory was sufficient.
    withheld_reason: str | None = None
    #: The §16.2 mode the search really ran in.
    mode: str = "unknown"
    #: The identifiers the run reuses as-is.
    information_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the projection the delivery, the audit and the UI share."""
        return {
            "sufficient": self.sufficient,
            "stopped_acquisition": self.stopped_acquisition,
            "criteria": list(self.criteria),
            "withheld_reason": self.withheld_reason,
            "mode": self.mode,
            "information_ids": list(self.information_ids),
        }


def early_stop_decision(
    result: MemoryResult,
    *,
    mode: str,
    limitations: Sequence[str] = (),
) -> EarlyStopDecision:
    """Decide whether *result* may stop the acquisition (§17.1, §8.4).

    Sufficiency alone is **not** enough, and this is the point of the function:

    * a lookup that ran in a **degraded mode** (lexical-only, i.e. the §16.2
      semantic half was unavailable) cannot conclude that the run already knows
      the answer: a handful of units that merely share words with the question
      must never stop a run;
    * a lookup that declared **limitations** (candidates without a vector, a
      partial comparison…) is treated the same way.

    In both cases the units are still reused — nothing is thrown away — but the
    acquisition keeps running: ``sufficient=True`` with
    ``stopped_acquisition=False`` and a ``withheld_reason`` that says why.

    Args:
        result: The §17.1 lookup outcome.
        mode: The §16.2 mode the search reported (``hybrid``, ``lexical_only``,
            ``unavailable``).
        limitations: What the search said it could not do.

    Returns:
        The decision, carrying its criteria and its reason.
    """
    identifiers = tuple(item.information_id for item in result.items)

    if not result.sufficient:
        return EarlyStopDecision(
            sufficient=False,
            stopped_acquisition=False,
            criteria=(),
            withheld_reason=result.reason or "mémoire insuffisante : aucun candidat réutilisable",
            mode=mode,
            information_ids=(),
        )

    if mode != SUFFICIENT_MODE:
        # §16.2 — a lexical hit is a guess about relevance, not a conclusion.
        return EarlyStopDecision(
            sufficient=True,
            stopped_acquisition=False,
            criteria=SUFFICIENCY_CRITERIA,
            withheld_reason=(
                f"recherche « {mode} » : la suffisance §17.1 n'est conclue qu'en mode "
                f"« {SUFFICIENT_MODE} » (une correspondance lexicale ne dit pas que la "
                "question est déjà répondue)"
            ),
            mode=mode,
            information_ids=identifiers,
        )

    if limitations:
        return EarlyStopDecision(
            sufficient=True,
            stopped_acquisition=False,
            criteria=SUFFICIENCY_CRITERIA,
            withheld_reason=(
                "recherche limitée (" + "; ".join(str(item) for item in limitations) + ")"
            ),
            mode=mode,
            information_ids=identifiers,
        )

    return EarlyStopDecision(
        sufficient=True,
        stopped_acquisition=True,
        criteria=SUFFICIENCY_CRITERIA,
        withheld_reason=None,
        mode=mode,
        information_ids=identifiers,
    )
