"""``hybrid_search`` internal tool per Â§21, weighted 0.6/0.4 per Â§16.2.

Hybrid retrieval needs an embedding of the query. INIS V1 does not embed text
itself, so the caller injects an ``embedder``. When no embedder is supplied the
tool performs **lexical-only** retrieval and records that fact in the returned
units' ``provenance["retrieval_mode"]`` (``"lexical_only"`` instead of
``"hybrid"``), so a degraded search can never be mistaken for a full one (Â§0.2).

Filter keys are restricted to an allow-list of real columns and always travel as
bound parameters: no filter value is ever interpolated into the statement.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.information_unit import InformationUnit
from app.tools.engine_access import resolve_engine
from app.tools.knowledge.unit_mapper import information_unit_from_row
from app.tools.knowledge.vector_searcher import OWNER_TYPE, _vector_literal

__all__ = ["hybrid_search"]

#: Â§16.2 weights.
DEFAULT_SEMANTIC_WEIGHT = 0.6
DEFAULT_LEXICAL_WEIGHT = 0.4

#: ``filters`` keys that map onto a real column; every other key is rejected.
FILTER_COLUMNS: dict[str, str] = {
    "source_id": "iu.source_id",
    "document_id": "iu.document_id",
    "dataset_id": "iu.dataset_id",
    "data_stage": "iu.data_stage",
    "type": "iu.type",
}

_UNIT_COLUMNS = (
    "iu.id AS id",
    "iu.type AS type",
    "iu.content AS content",
    "iu.source_id AS source_id",
    "iu.document_id AS document_id",
    "iu.data_stage AS data_stage",
    "iu.created_at AS created_at",
)

#: Async callable turning a query string into an embedding.
Embedder = Callable[[str], Awaitable[Sequence[float]]]


def _filter_clause(filters: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Return the SQL ``AND`` fragment and its bound parameters for *filters*.

    Raises:
        ValidationError: If a filter key is not in :data:`FILTER_COLUMNS`.
    """
    if not filters:
        return "", {}
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key, value in filters.items():
        column = FILTER_COLUMNS.get(str(key))
        if column is None:
            raise ValidationError(
                f"unsupported filter '{key}' "
                f"(allowed: {', '.join(sorted(FILTER_COLUMNS))})"
            )
        params[key] = value
        clauses.append(f"{column} = :{key}")
    return " AND " + " AND ".join(clauses), params


async def hybrid_search(
    query: str,
    filters: Mapping[str, Any] | None = None,
    *,
    limit: int = 10,
    embedder: Embedder | None = None,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
) -> list[InformationUnit]:
    """Return the information units matching *query* (Â§21, Â§16.2).

    Args:
        query: Query text.
        filters: Optional equality filters over :data:`FILTER_COLUMNS`.
        limit: Maximum number of results.
        embedder: Async callable embedding the query. When omitted, retrieval is
            lexical-only and the returned provenance says so.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.
        semantic_weight: Weight of the semantic component (Â§16.2 default 0.6).
        lexical_weight: Weight of the lexical component (Â§16.2 default 0.4).

    Returns:
        The merged results, best combined score first.

    Raises:
        ValidationError: If *query* is empty, *limit* < 1, a filter key is
            unknown, or a weight is negative.
        InfrastructureError: If no engine is available or a query fails.
    """
    if not query or not str(query).strip():
        raise ValidationError("query must be a non-empty string")
    if limit < 1:
        raise ValidationError("limit must be >= 1")
    if semantic_weight < 0 or lexical_weight < 0:
        raise ValidationError("weights must be non-negative")

    clause, filter_params = _filter_clause(filters)
    active_engine = resolve_engine(engine, connection_string, component="hybrid_search")

    lexical_statement = text(
        f"""
        SELECT {", ".join(_UNIT_COLUMNS)},
               ts_rank(iu.search_vector, plainto_tsquery(:query)) AS lexical_score
        FROM information_units AS iu
        WHERE iu.search_vector @@ plainto_tsquery(:query){clause}
        ORDER BY lexical_score DESC
        LIMIT :limit
        """
    )
    try:
        async with active_engine.connect() as connection:
            lexical_result = await connection.execute(
                lexical_statement,
                {"query": query, "limit": limit, **filter_params},
            )
            lexical_rows = [dict(row) for row in lexical_result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"hybrid_search lexical query failed: {exc}") from exc

    rows_by_id: dict[str, dict] = {}
    lexical_scores: dict[str, float] = {}
    for row in lexical_rows:
        identifier = str(row.get("id"))
        rows_by_id[identifier] = row
        lexical_scores[identifier] = float(row.get("lexical_score") or 0.0)

    mode = "lexical_only"
    semantic_scores: dict[str, float] = {}
    if embedder is not None:
        mode = "hybrid"
        literal = _vector_literal(await embedder(query))
        semantic_statement = text(
            f"""
            SELECT {", ".join(_UNIT_COLUMNS)},
                   1 - (e.vector <=> CAST(:query_vector AS vector)) AS similarity
            FROM embeddings AS e
            JOIN information_units AS iu ON iu.id = e.owner_id
            WHERE e.owner_type = :owner_type{clause}
            ORDER BY e.vector <=> CAST(:query_vector AS vector)
            LIMIT :limit
            """
        )
        try:
            async with active_engine.connect() as connection:
                semantic_result = await connection.execute(
                    semantic_statement,
                    {
                        "query_vector": literal,
                        "owner_type": OWNER_TYPE,
                        "limit": limit,
                        **filter_params,
                    },
                )
                semantic_rows = [dict(row) for row in semantic_result.mappings().all()]
        except Exception as exc:
            raise InfrastructureError(
                f"hybrid_search semantic query failed: {exc}"
            ) from exc

        for row in semantic_rows:
            identifier = str(row.get("id"))
            rows_by_id.setdefault(identifier, row)
            semantic_scores[identifier] = float(row.get("similarity") or 0.0)

    scored: list[tuple[float, InformationUnit]] = []
    for identifier, row in rows_by_id.items():
        lexical = lexical_scores.get(identifier, 0.0)
        semantic = semantic_scores.get(identifier, 0.0)
        combined = (semantic * semantic_weight) + (lexical * lexical_weight)
        clean_row = {
            key: value
            for key, value in row.items()
            if key not in {"lexical_score", "similarity"}
        }
        unit = information_unit_from_row(
            clean_row,
            extra_provenance={
                "retrieval_mode": mode,
                "semantic_score": round(semantic, 6),
                "lexical_score": round(lexical, 6),
                "combined_score": round(combined, 6),
            },
        )
        scored.append((combined, unit))

    scored.sort(key=lambda item: (-item[0], item[1].information_id))
    return [unit for _score, unit in scored[:limit]]
