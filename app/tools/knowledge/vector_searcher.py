"""``vector_search`` internal tool per Â§21, backed by pgvector (Â§16.1).

The signature is ``vector_search(query_vector, limit)``; the caller supplies the
embedding because INIS V1 does not embed text itself. The query joins
``embeddings`` with ``information_units`` so the caller receives real
``InformationUnit`` values carrying the cosine similarity in their
``provenance`` (Â§14.1), instead of bare identifiers.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.information_unit import InformationUnit
from app.tools.engine_access import resolve_engine
from app.tools.knowledge.unit_mapper import information_unit_from_row

__all__ = ["vector_search"]

#: Owner type used by the Â§16 embeddings table for information units.
OWNER_TYPE = "information_unit"

_UNIT_COLUMNS = (
    "iu.id AS id",
    "iu.type AS type",
    "iu.content AS content",
    "iu.source_id AS source_id",
    "iu.document_id AS document_id",
    "iu.data_stage AS data_stage",
    "iu.created_at AS created_at",
)


def _vector_literal(query_vector: Sequence[float]) -> str:
    """Return the pgvector text literal for *query_vector*.

    Args:
        query_vector: Embedding values.

    Returns:
        A ``[a,b,c]`` literal.

    Raises:
        ValidationError: If the vector is empty or contains non-numeric values.
    """
    if not query_vector:
        raise ValidationError("query_vector must not be empty")
    parts: list[str] = []
    for value in query_vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(
                f"query_vector must contain only numbers, got {type(value).__name__}"
            )
        parts.append(repr(float(value)))
    return "[" + ",".join(parts) + "]"


async def vector_search(
    query_vector: Sequence[float],
    limit: int = 10,
    *,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
    owner_type: str = OWNER_TYPE,
) -> list[InformationUnit]:
    """Return the *limit* nearest information units to *query_vector* (Â§21, Â§16.1).

    Args:
        query_vector: Embedding of the query.
        limit: Maximum number of results.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.
        owner_type: ``embeddings.owner_type`` to restrict the search to.

    Returns:
        The nearest units, best cosine similarity first, each carrying
        ``provenance["similarity"]`` and ``provenance["retrieval"] = "vector"``.

    Raises:
        ValidationError: If the vector is invalid or *limit* < 1.
        InfrastructureError: If no engine is available or the query fails.
    """
    if limit < 1:
        raise ValidationError("limit must be >= 1")
    literal = _vector_literal(query_vector)

    active_engine = resolve_engine(engine, connection_string, component="vector_search")
    statement = text(
        f"""
        SELECT {", ".join(_UNIT_COLUMNS)},
               1 - (e.vector <=> CAST(:query_vector AS vector)) AS similarity
        FROM embeddings AS e
        JOIN information_units AS iu ON iu.id = e.owner_id
        WHERE e.owner_type = :owner_type
        ORDER BY e.vector <=> CAST(:query_vector AS vector)
        LIMIT :limit
        """  # nosec: B608
    )
    try:
        async with active_engine.connect() as connection:
            result = await connection.execute(
                statement,
                {"query_vector": literal, "owner_type": owner_type, "limit": limit},
            )
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"vector_search failed: {exc}") from exc

    units: list[InformationUnit] = []
    for row in rows:
        similarity = row.pop("similarity", None)
        unit = information_unit_from_row(
            row,
            extra_provenance={
                "retrieval": "vector",
                "similarity": round(float(similarity), 6)
                if similarity is not None
                else None,
            },
        )
        units.append(unit)
    return units
