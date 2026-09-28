"""``locate_fragment`` and ``retrieve_context`` internal tools per Â§21.

Both read stored ``information_units`` rows and rebuild the Â§11 entities:

* :func:`locate_fragment` ranks the units of one document against a query using
  a lexical overlap score computed in Python, so its behaviour does not depend
  on a PostgreSQL text-search configuration being installed;
* :func:`retrieve_context` returns the units whose identifiers were supplied,
  preserving the requested order â€” an identifier matching no row is simply
  absent from the result.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.information_unit import InformationUnit
from app.tools.engine_access import resolve_engine
from app.tools.knowledge.unit_mapper import information_unit_from_row

__all__ = ["lexical_overlap", "locate_fragment", "retrieve_context"]

#: Columns read from ``information_units`` (Â§27 minimum).
_UNIT_COLUMNS = (
    "id",
    "type",
    "content",
    "source_id",
    "document_id",
    "data_stage",
    "created_at",
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(value: str) -> set[str]:
    """Return the lower-cased word set of *value*."""
    return {match.group(0).lower() for match in _WORD_RE.finditer(value or "")}


def lexical_overlap(query: str, candidate: str) -> float:
    """Return the Jaccard overlap between the query and candidate word sets.

    Args:
        query: User query text.
        candidate: Candidate fragment text.

    Returns:
        A score in ``[0.0, 1.0]``; ``0.0`` when either side has no word.
    """
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    return len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)


def _unit_text(unit: InformationUnit) -> str:
    """Return the searchable text of *unit* (its ``content`` values, flattened)."""
    pieces: list[str] = []
    for value in unit.content.values():
        if isinstance(value, str):
            pieces.append(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            pieces.append(str(value))
    return " ".join(pieces)


async def locate_fragment(
    document_id: str,
    query: str,
    *,
    limit: int = 10,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
) -> list[InformationUnit]:
    """Return the units of *document_id* most related to *query* (Â§21).

    Args:
        document_id: ``DOC_{ULID}`` identifier of the document to search.
        query: Query text.
        limit: Maximum number of fragments returned.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        The matching units, best overlap first, with ``provenance`` carrying the
        computed ``lexical_overlap`` score (traceable retrieval, Â§14.1).

    Raises:
        ValidationError: If *document_id* or *query* is empty, or *limit* < 1.
        InfrastructureError: If no PostgreSQL engine is available or the query
            fails.
    """
    if not document_id or not str(document_id).strip():
        raise ValidationError("document_id must be a non-empty string")
    if not query or not str(query).strip():
        raise ValidationError("query must be a non-empty string")
    if limit < 1:
        raise ValidationError("limit must be >= 1")

    active_engine = resolve_engine(
        engine, connection_string, component="locate_fragment"
    )
    statement = text(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM information_units "
        "WHERE document_id = :document_id"  # nosec: B608
    )
    try:
        async with active_engine.connect() as connection:
            result = await connection.execute(statement, {"document_id": document_id})
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"locate_fragment failed: {exc}") from exc

    scored: list[tuple[float, InformationUnit]] = []
    for row in rows:
        unit = information_unit_from_row(row)
        score = lexical_overlap(query, _unit_text(unit))
        unit.provenance["retrieval"] = "lexical_overlap"
        unit.provenance["lexical_overlap"] = round(score, 6)
        scored.append((score, unit))

    scored.sort(key=lambda item: (-item[0], item[1].information_id))
    return [unit for _score, unit in scored[:limit]]


async def retrieve_context(
    ids: Sequence[str],
    *,
    engine: AsyncEngine | None = None,
    connection_string: str | None = None,
) -> list[InformationUnit]:
    """Return the information units whose identifiers are in *ids* (Â§21).

    Args:
        ids: ``INF_{ULID}`` identifiers to retrieve.
        engine: Optional pre-built async engine.
        connection_string: PostgreSQL URL used when *engine* is omitted.

    Returns:
        The found units, in the order the identifiers were requested.

    Raises:
        InfrastructureError: If no PostgreSQL engine is available or the query
            fails.
    """
    requested = [str(identifier) for identifier in ids if identifier]
    if not requested:
        return []

    active_engine = resolve_engine(
        engine, connection_string, component="retrieve_context"
    )
    statement = text(
        f"SELECT {', '.join(_UNIT_COLUMNS)} FROM information_units WHERE id = ANY(:ids)"  # nosec: B608
    )
    try:
        async with active_engine.connect() as connection:
            result = await connection.execute(statement, {"ids": requested})
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"retrieve_context failed: {exc}") from exc

    by_id = {str(row.get("id")): information_unit_from_row(row) for row in rows}
    return [by_id[identifier] for identifier in requested if identifier in by_id]
