"""§16.2/ADR 004 — hybrid search: 0.6 semantic + 0.4 lexical, and honest about what it ran.

The ADR fixes the formula ``0.6 * score_vectoriel + 0.4 * score_lexical`` and,
in the same line, its precondition: *each sub-score is brought back into
``[0, 1]`` before weighting*. The implementation this module replaces did
neither part correctly — it weighted a raw ``ts_rank`` (unbounded) against a
cosine similarity (bounded), so a document repeating a rare word could outrank a
semantically identical one, and the weights were unverifiable.

Three defects are fixed here:

* **normalisation**: each side is divided by the best score of its own candidate
  set (a window function), so the weighted sum really is a ``[0, 1]`` blend;
* **the sub-scores are returned**: a caller (and a test) recomputes
  ``0.6 * semantic + 0.4 * lexical`` on the row instead of trusting a single
  opaque number;
* **degradation is stated**: with no engine, no stored vector or no query
  vector, the search answers the lexical half **alone** — and says so in
  ``limitations`` through :class:`HybridSearchOutcome`, instead of pretending a
  hybrid ranking happened. ``search`` keeps returning a bare list for callers
  that only need the rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.storage.database.engine import create_engine_or_none

__all__ = [
    "DEFAULT_OWNER_TYPE",
    "LEXICAL_WEIGHT",
    "SEMANTIC_WEIGHT",
    "HybridSearch",
    "HybridSearchOutcome",
]

#: §16.1 — ``embeddings.owner_type`` of an ``InformationUnit`` (``vector_searcher``).
DEFAULT_OWNER_TYPE = "information_unit"

#: ADR 004 — weights of the canonical fusion formula (§16.2).
SEMANTIC_WEIGHT = 0.6
LEXICAL_WEIGHT = 0.4

#: Rows each sub-search may propose before the fusion (§41.13 style bound).
DEFAULT_CANDIDATES = 100

_HYBRID_SQL = text(
    """
    WITH semantic AS (
        SELECT e.owner_id AS owner_id,
               GREATEST(0.0, LEAST(1.0, 1 - (e.vector <=> CAST(:query_vector AS vector))))
                   AS raw_score
        FROM embeddings AS e
        WHERE e.owner_type = :owner_type
          AND (CAST(:source_id AS text) IS NULL OR EXISTS (
                SELECT 1 FROM information_units AS iu
                WHERE iu.id = e.owner_id AND iu.source_id = :source_id
          ))
        ORDER BY e.vector <=> CAST(:query_vector AS vector)
        LIMIT :candidates
    ),
    semantic_norm AS (
        SELECT owner_id,
               CASE WHEN max(raw_score) OVER () > 0
                    THEN raw_score / max(raw_score) OVER () ELSE 0 END AS score
        FROM semantic
    ),
    lexical AS (
        SELECT iu.id AS owner_id,
               ts_rank(iu.search_vector, plainto_tsquery(:query)) AS raw_score
        FROM information_units AS iu
        WHERE iu.search_vector @@ plainto_tsquery(:query)
          AND (CAST(:source_id AS text) IS NULL OR iu.source_id = :source_id)
        ORDER BY raw_score DESC
        LIMIT :candidates
    ),
    lexical_norm AS (
        SELECT owner_id,
               CASE WHEN max(raw_score) OVER () > 0
                    THEN raw_score / max(raw_score) OVER () ELSE 0 END AS score
        FROM lexical
    )
    SELECT COALESCE(s.owner_id, l.owner_id) AS owner_id,
           COALESCE(s.score, 0) AS semantic_score,
           COALESCE(l.score, 0) AS lexical_score,
           LEAST(
               1.0,
               COALESCE(s.score, 0) * CAST(:semantic_weight AS double precision)
                 + COALESCE(l.score, 0) * CAST(:lexical_weight AS double precision)
           ) AS final_score
    FROM semantic_norm AS s
    FULL OUTER JOIN lexical_norm AS l USING (owner_id)
    ORDER BY final_score DESC, owner_id
    LIMIT :limit
    """  # nosec: B608 - no user input is interpolated
)

_LEXICAL_ONLY_SQL = text(
    """
    WITH lexical AS (
        SELECT iu.id AS owner_id,
               ts_rank(iu.search_vector, plainto_tsquery(:query)) AS raw_score
        FROM information_units AS iu
        WHERE iu.search_vector @@ plainto_tsquery(:query)
          AND (CAST(:source_id AS text) IS NULL OR iu.source_id = :source_id)
        ORDER BY raw_score DESC
        LIMIT :candidates
    )
    SELECT owner_id,
           0.0 AS semantic_score,
           CASE WHEN max(raw_score) OVER () > 0
                THEN raw_score / max(raw_score) OVER () ELSE 0 END AS lexical_score,
           CASE WHEN max(raw_score) OVER () > 0
                THEN raw_score / max(raw_score) OVER () ELSE 0 END AS final_score
    FROM lexical
    ORDER BY final_score DESC, owner_id
    LIMIT :limit
    """  # nosec: B608 - no user input is interpolated
)

_COUNT_EMBEDDINGS = text(
    """
    SELECT count(*) AS total
    FROM embeddings
    WHERE owner_type = :owner_type
    """
)


@dataclass(frozen=True)
class HybridSearchOutcome:
    """What one §16.2 search really ran, and what it found.

    ``mode`` is ``"hybrid"`` when both halves contributed, ``"lexical_only"``
    when the semantic half could not run (no engine, no stored vector, no query
    vector) and ``"unavailable"`` when neither could. ``limitations`` states the
    reason, so a caller never has to guess why a result set looks lexical.
    """

    rows: tuple[dict[str, Any], ...] = ()
    mode: str = "hybrid"
    limitations: tuple[str, ...] = ()
    weights: dict[str, float] = field(default_factory=dict)

    def ids(self) -> list[str]:
        """Return the ``owner_id`` of every row, best score first."""
        return [str(row.get("owner_id")) for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection carried by the delivery."""
        return {
            "mode": self.mode,
            "results": len(self.rows),
            "weights": dict(self.weights),
            "limitations": list(self.limitations),
        }


class HybridSearch:
    """§16.2 — pgvector + full-text fusion, at the ADR 004 weights."""

    def __init__(
        self,
        connection_string: str = "",
        *,
        engine: AsyncEngine | None = None,
        owner_type: str = DEFAULT_OWNER_TYPE,
        semantic_weight: float = SEMANTIC_WEIGHT,
        lexical_weight: float = LEXICAL_WEIGHT,
    ) -> None:
        """Initialize the hybrid search.

        Args:
            connection_string: PostgreSQL connection string, used when *engine*
                is omitted.
            engine: Pre-built async engine, used as-is when supplied (the
                pipeline shares its engine with the rest of the run).
            owner_type: ``embeddings.owner_type`` the semantic half reads.
            semantic_weight: Weight of the vector sub-score (ADR 004: ``0.6``).
            lexical_weight: Weight of the full-text sub-score (ADR 004: ``0.4``).

        Raises:
            ValueError: When a weight is negative or both are zero — a weighted
                sum that can never rank anything is a bug, not a configuration.
        """
        if semantic_weight < 0 or lexical_weight < 0:
            raise ValueError("weights must not be negative (§16.2)")
        if semantic_weight == 0 and lexical_weight == 0:
            raise ValueError("at least one weight must be positive (§16.2)")
        self._connection_string = connection_string
        self._owner_type = owner_type
        self._semantic_weight = float(semantic_weight)
        self._lexical_weight = float(lexical_weight)
        self._engine: AsyncEngine | None = engine

    @property
    def weights(self) -> dict[str, float]:
        """Return the effective fusion weights."""
        return {"semantic": self._semantic_weight, "lexical": self._lexical_weight}

    async def _get_engine(self) -> AsyncEngine | None:
        """Get or create the async engine. Returns None in degraded mode."""
        if self._engine is None:
            self._engine = create_engine_or_none(self._connection_string)
        return self._engine

    async def _has_embeddings(self, connection: Any) -> bool:
        """Return whether any vector is stored for ``owner_type`` (§16.1)."""
        result = await connection.execute(
            _COUNT_EMBEDDINGS, {"owner_type": self._owner_type}
        )
        row = result.mappings().first()
        return bool(row and int(row["total"]) > 0)

    async def search_outcome(
        self,
        query: str,
        query_vector: list[float] | None = None,
        limit: int = 10,
        *,
        filters: dict[str, Any] | None = None,
        candidates: int = DEFAULT_CANDIDATES,
    ) -> HybridSearchOutcome:
        """Run the §16.2 search and report which halves really ran.

        Args:
            query: Text query for the lexical half.
            query_vector: Query embedding for the semantic half. ``None`` asks
                the lexical half alone (§17.1 reuse still works without a
                provider) and the outcome says so.
            limit: Maximum number of fused rows returned.
            filters: Optional ``{"source_id": …}`` restriction, applied to both
                halves (§17.1 ``filters``).
            candidates: Rows each half may propose before the fusion.

        Returns:
            A :class:`HybridSearchOutcome`. Never raises on an unreachable or
            empty database: the mode and the limitation carry the truth.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        source_id = str((filters or {}).get("source_id") or "") or None
        engine = await self._get_engine()
        if engine is None:
            return HybridSearchOutcome(
                mode="unavailable",
                weights=self.weights,
                limitations=(
                    (
                        "Recherche §16.2 indisponible (aucune base PostgreSQL "
                        "configurée) : aucune mémoire n'a été consultée."
                    ),
                ),
            )
        try:
            async with engine.connect() as connection:
                has_vectors = await self._has_embeddings(connection)
                use_semantic = bool(query_vector) and has_vectors
                parameters: dict[str, Any] = {
                    "query": query,
                    "limit": limit,
                    "candidates": max(1, int(candidates)),
                    "source_id": source_id,
                    "owner_type": self._owner_type,
                }
                if use_semantic:
                    parameters["query_vector"] = _vector_literal(query_vector or [])
                    parameters["semantic_weight"] = self._semantic_weight
                    parameters["lexical_weight"] = self._lexical_weight
                    statement = _HYBRID_SQL
                else:
                    statement = _LEXICAL_ONLY_SQL
                result = await connection.execute(statement, parameters)
                rows = tuple(dict(row) for row in result.mappings().all())
        except Exception as exc:  # noqa: BLE001 - §25.2: a failed search is stated
            return HybridSearchOutcome(
                mode="unavailable",
                weights=self.weights,
                limitations=(
                    (
                        f"Recherche §16.2 impossible ({type(exc).__name__}: {exc}) : "
                        "aucune mémoire n'a été consultée."
                    ),
                ),
            )
        if use_semantic:
            return HybridSearchOutcome(rows=rows, mode="hybrid", weights=self.weights)
        if not query_vector:
            reason = (
                "Aucun vecteur de requête fourni : recherche **lexicale seule** "
                "(les poids 0.6/0.4 de §16.2 ne s'appliquent qu'à une fusion)."
            )
        else:
            reason = (
                "Aucun embedding stocké pour cette base (§16.1) : recherche "
                "**lexicale seule**, la moitié sémantique de §16.2 n'a pas pu "
                "s'exécuter."
            )
        return HybridSearchOutcome(
            rows=rows, mode="lexical_only", weights=self.weights, limitations=(reason,)
        )

    async def search(
        self,
        query: str,
        query_vector: list[float] | None = None,
        limit: int = 10,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Return the fused rows only (``[]`` when nothing could run).

        Kept for callers that need no mode: prefer :meth:`search_outcome`, which
        also says *what* ran. ``query_vector`` may be ``None`` to search the
        lexical half alone, exactly as the §17.1 memory path does without an
        embeddings provider.
        """
        outcome = await self.search_outcome(query, query_vector, limit, filters=filters)
        return [dict(row) for row in outcome.rows]


def _vector_literal(query_vector: list[float]) -> str:
    """Return the pgvector text literal ``[a,b,c]`` of *query_vector*."""
    return "[" + ",".join(repr(float(value)) for value in query_vector) + "]"


