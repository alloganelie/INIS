"""§17.1 — the memory search the pipeline injects into ``memory_checker``.

``memory_checker.memory_lookup`` decides *whether* an already-acquired unit
answers a question; it takes its candidates from an injected callable
(:data:`~app.planning.memory_checker.MemorySearch`) precisely so the decision
stays testable. This module is that callable: the §16.2 hybrid search over the
persisted §11 units, mapped onto the §17.1 :class:`MemoryCandidate` fields the
filter chain inspects.

Three rules make the answer trustworthy:

* **the §11 payload is rebuilt, not guessed**: candidates are built from
  :func:`app.tools.knowledge.fragment_locator.retrieve_context`, so the
  provenance the filter chain reads is the one stored with the unit (§0.2);
* **the freshness is a fact or it is absent**: ``sources.freshness`` when the
  source records one, otherwise the unit's own ``created_at`` — the instant INIS
  learned it. An unknown age stays unknown, and the §17.1 threshold then refuses
  the candidate instead of assuming it is fresh;
* **what the search really ran is exposed**: ``mode`` and ``limitations`` come
  from :class:`~app.storage.search.hybrid_search.HybridSearchOutcome`, so a run
  without embeddings says « recherche lexicale seule » in its colimitations
  instead of pretending the semantic half contributed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.core.errors import InfrastructureError
from app.domain.entities.memory_result import MemoryCandidate
from app.planning.memory_checker import MemoryRequirements
from app.storage.database.engine import create_engine_or_none, get_default_engine
from app.storage.search.hybrid_search import (
    DEFAULT_OWNER_TYPE,
    HybridSearch,
    HybridSearchOutcome,
)
from app.tools.knowledge.fragment_locator import retrieve_context

__all__ = [
    "HybridMemorySearch",
    "candidate_from_unit",
    "freshness_of_source",
    "memory_audit_payload",
]

#: §17.1 — how many candidates the search may propose to the filter chain.
DEFAULT_MEMORY_LIMIT = 10

_FRESHNESS_SQL = text(
    """
    SELECT id, freshness
    FROM sources
    WHERE id = ANY(:ids)
    """
)

#: Keys a ``sources.freshness`` payload may use to date the observation (§41.5).
_FRESHNESS_KEYS: tuple[str, ...] = (
    "last_checked",
    "checked_at",
    "observed_at",
    "retrieved_at",
    "updated_at",
    "timestamp",
)


def _as_datetime(value: Any) -> datetime | None:
    """Return *value* as a timezone-aware datetime, or ``None`` when unreadable."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def freshness_of_source(freshness: Any) -> datetime | None:
    """Return the observation date carried by a ``sources.freshness`` payload.

    The column is JSONB with no fixed shape in the schema, so the known keys are
    tried in order and anything else yields ``None``: an unreadable payload must
    not become a plausible date (§0.2).
    """
    if isinstance(freshness, str):
        return _as_datetime(freshness)
    if not isinstance(freshness, Mapping):
        return None
    for key in _FRESHNESS_KEYS:
        moment = _as_datetime(freshness.get(key))
        if moment is not None:
            return moment
    return None


def candidate_from_unit(
    unit: Any,
    *,
    score: float | None = None,
    source_freshness: datetime | None = None,
) -> MemoryCandidate:
    """Return the §17.1 candidate carried by one retrieved §11 *unit*.

    Args:
        unit: An ``InformationUnit`` (or its mapping) returned by
            ``retrieve_context``.
        score: Final §16.2 score of the row, kept in ``provenance`` so the
            delivery can explain why this candidate came first.
        source_freshness: Date read from ``sources.freshness``; when absent the
            unit's own ``created_at`` is used — the instant INIS learned it.

    Returns:
        The candidate the filter chain evaluates.
    """
    data = unit.model_dump() if hasattr(unit, "model_dump") else dict(unit)
    provenance = dict(data.get("provenance") or {})
    if score is not None:
        provenance["retrieval_score"] = score
    provenance.setdefault("source_id", data.get("source_id"))
    return MemoryCandidate(
        information_id=str(data.get("information_id") or ""),
        content=dict(data.get("content") or {}),
        source_id=data.get("source_id"),
        provenance=provenance,
        data_stage=str(data.get("data_stage") or "normalized"),
        source_freshness=source_freshness or _as_datetime(data.get("created_at")),
        # §18.2 — ``information_units`` carries no soft-delete column today (the
        # schema has one on ``accounts``/``sessions`` only), so a stored unit is
        # not deleted: the flag is stated, never assumed from a missing column.
        deleted=False,
        policy_allows_reuse=True,
    )


class HybridMemorySearch:
    """The §17.1 ``hybrid_search`` callable, injected into ``memory_lookup``.

    It is a callable object rather than a closure because the run has to report
    *what the search ran*: :attr:`mode` and :attr:`limitations` are filled by the
    last call and read by the pipeline to build the delivery.
    """

    def __init__(
        self,
        *,
        connection_string: str | None = None,
        engine: Any | None = None,
        owner_type: str = DEFAULT_OWNER_TYPE,
        limit: int = DEFAULT_MEMORY_LIMIT,
        query_vector: Sequence[float] | None = None,
    ) -> None:
        """Initialize the search.

        Args:
            connection_string: PostgreSQL URL; ``INIS_DATABASE_URL`` when omitted.
            engine: Pre-built async engine, used as-is when supplied.
            owner_type: ``embeddings.owner_type`` the semantic half reads.
            limit: Candidates proposed to the filter chain.
            query_vector: Optional question embedding. Without one the search is
                lexical only, and says so (§16.1 has no local embedding model).
        """
        self._engine = engine
        self._connection_string = connection_string
        self._limit = max(1, int(limit))
        self._query_vector = list(query_vector) if query_vector else None
        self._search = HybridSearch(
            connection_string or "", engine=engine, owner_type=owner_type
        )
        #: Mode of the last call: ``hybrid``/``lexical_only``/``unavailable``.
        self.mode: str = "unavailable"
        #: Limitations of the last call, copied into the delivery (§25.2).
        self.limitations: list[str] = []
        #: The raw §16.2 outcome of the last call (scores included).
        self.outcome: HybridSearchOutcome | None = None
        #: The §11 payloads the last call materialised, by identifier: the run
        #: reuses these units as they are (§17.1 — no copy, no new identifier).
        self.units: dict[str, dict[str, Any]] = {}

    async def _connection(self) -> Any | None:
        """Return the engine to query with, or ``None`` when none is usable."""
        if self._engine is not None:
            return self._engine
        if self._connection_string:
            self._engine = create_engine_or_none(self._connection_string)
            return self._engine
        self._engine = get_default_engine()
        return self._engine

    async def _freshness(
        self, engine: Any, source_ids: Sequence[str]
    ) -> dict[str, datetime | None]:
        """Return ``sources.freshness`` per source id, tolerating a missing table."""
        wanted = [str(source_id) for source_id in source_ids if source_id]
        if not wanted:
            return {}
        try:
            async with engine.connect() as connection:
                result = await connection.execute(_FRESHNESS_SQL, {"ids": wanted})
                rows = result.mappings().all()
        except Exception:  # noqa: BLE001 - unreadable freshness stays unknown
            return {}
        return {str(row["id"]): freshness_of_source(row["freshness"]) for row in rows}

    async def __call__(
        self, question: str, requirements: MemoryRequirements
    ) -> list[MemoryCandidate]:
        """Return the candidates of *question*, best §16.2 score first (§17.1)."""
        outcome = await self._search.search_outcome(
            question,
            self._query_vector,
            self._limit,
            filters=dict(requirements.filters or {}),
        )
        self.outcome = outcome
        self.mode = outcome.mode
        self.limitations = list(outcome.limitations)
        if not outcome.rows:
            return []
        engine = await self._connection()
        if engine is None:
            self.mode = "unavailable"
            self.limitations.append(
                "Mémoire §17.1 non consultable (aucune base PostgreSQL configurée) : "
                "la recherche §16.2 n'a pas pu s'exécuter."
            )
            return []
        ids = outcome.ids()
        try:
            units = await retrieve_context(ids, engine=engine)
        except InfrastructureError as exc:
            self.mode = "unavailable"
            self.limitations.append(
                f"Mémoire §17.1 non reconstruite ({exc}) : les unités retrouvées "
                "n'ont pas pu être relues (§21 retrieve_context)."
            )
            return []
        freshness = await self._freshness(
            engine, [getattr(unit, "source_id", None) or "" for unit in units]
        )
        scores = {str(row.get("owner_id")): row.get("final_score") for row in outcome.rows}
        self.units = {unit.information_id: unit.model_dump() for unit in units}
        return [
            candidate_from_unit(
                unit,
                score=_as_float(scores.get(unit.information_id)),
                source_freshness=freshness.get(str(unit.source_id or "")),
            )
            for unit in units
        ]


def _as_float(value: Any) -> float | None:
    """Return *value* as a float, or ``None`` when it is not a number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def memory_audit_payload(
    request_id: str,
    memory_note: Any,
    *,
    mode: str,
    limit: int = DEFAULT_MEMORY_LIMIT,
) -> dict[str, Any]:
    """Return the §20 audit event describing one §17.1 memory lookup.

    « Mémoire utilisée » must be auditable: the event names the request, the
    result (``success`` when an existing unit was reused, ``degraded`` when the
    run had to acquire from scratch), how many candidates were kept and in which
    mode the search ran — a lexical-only answer must never look like a hybrid one
    in the audit trail (§16.2, §0.2).

    Args:
        request_id: The request the lookup belongs to.
        memory_note: The ``MemoryResult.to_dict()`` projection of the lookup
            (``sufficient``, ``reason``, ``information_ids``).
        mode: The §16.2 mode the search reported (``hybrid``, ``lexical_only``,
            ``unavailable``).
        limit: The candidate bound that was configured.

    Returns:
        The payload ``AuditWriter.write`` expects.
    """
    note: Mapping[str, Any] = memory_note if isinstance(memory_note, Mapping) else {}
    sufficient = bool(note.get("sufficient"))
    reused = [str(identifier) for identifier in (note.get("information_ids") or [])]
    if sufficient:
        reason = (
            f"Mémoire §17.1 consultée en mode « {mode} » sur {limit} candidat(s) : "
            f"unité(s) réutilisée(s) {reused}"
        )
    else:
        reason = (
            f"Mémoire §17.1 consultée en mode « {mode} » sur {limit} candidat(s) : "
            f"{note.get('reason') or 'rien de réutilisable'}"
        )
    return {
        "actor_type": "pipeline",
        "actor_id": "agent:pipeline_runner",
        "action": "memory_lookup",
        "resource_type": "information_unit",
        "resource_id": reused[0] if reused else request_id,
        "request_id": request_id,
        "result": "success" if sufficient else "degraded",
        "reason": reason,
    }


