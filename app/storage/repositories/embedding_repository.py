"""Persistence of the §16.1 embeddings, read by the §16.2 searchers.

The table belongs to revision ``0003`` (``embedding_id UUID``, ``owner_type``,
``owner_id``, ``model``, a pgvector column of width 1536, ``metadata JSONB``,
``created_at``) and its HNSW cosine index. Nothing here creates it: on
PostgreSQL the schema comes from Alembic (§41.14), and the ``vector`` type does
not exist elsewhere — a schema invented by ``create_all`` would be a schema the
migration never planned.

Two rules shape the SQL:

* the vector is always handed over as a pgvector literal and cast explicitly
  (``CAST(:vector AS vector)``): a JSON array silently fails there, and that
  failure used to be invisible;
* every insert is ``ON CONFLICT (embedding_id) DO NOTHING``, so a run and the
  backfill can cover the same unit without ever duplicating a vector.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import bindparam, text

from app.core.time import utc_now
from app.storage.repositories.table_repository import as_dict, as_iso

__all__ = [
    "DEFAULT_DATA_STAGES",
    "EmbeddingRepository",
    "parse_vector",
    "to_embedding_response",
    "to_unit_row",
]

#: §12 stages whose text deserves a vector: ``raw`` is untouched material.
DEFAULT_DATA_STAGES: tuple[str, ...] = ("normalized", "enriched", "derived")

_INSERT = text(
    """
    INSERT INTO embeddings (
        embedding_id, owner_type, owner_id, model, vector, metadata, created_at
    ) VALUES (
        CAST(:embedding_id AS uuid), :owner_type, :owner_id, :model,
        CAST(:vector AS vector), CAST(:metadata AS JSONB), :created_at
    )
    ON CONFLICT (embedding_id) DO NOTHING
    """
)

_SELECT_COLUMNS = (
    "embedding_id, owner_type, owner_id, model, metadata, created_at, "
    "vector_dims(vector) AS dimensions"
)

_LIST_FOR_OWNER = text(
    f"""
    SELECT {_SELECT_COLUMNS}
    FROM embeddings
    WHERE owner_type = :owner_type AND owner_id = :owner_id
    ORDER BY created_at DESC
    LIMIT :limit
    """  # nosec: B608 - the interpolated fragment is a fixed column list
)

#: §41.5 L3 — read one vector **with its values** (the reuse lookup).
_SELECT_ONE = text(
    f"""
    SELECT {_SELECT_COLUMNS}, vector::text AS vector
    FROM embeddings
    WHERE embedding_id = CAST(:embedding_id AS uuid)
    """  # nosec: B608 - the interpolated fragment is a fixed column list
)

_COUNT = text(
    """
    SELECT count(*) AS total
    FROM embeddings
    WHERE owner_type = :owner_type
    """
)

_MISSING_UNITS = text(
    """
    SELECT iu.id AS information_id, iu.type, iu.content, iu.source_id,
           iu.document_id, iu.data_stage, iu.created_at
    FROM information_units AS iu
    LEFT JOIN embeddings AS e
           ON e.owner_id = iu.id AND e.owner_type = :owner_type
    WHERE e.embedding_id IS NULL
      AND iu.deleted_at IS NULL
      AND iu.data_stage IN :stages
    ORDER BY iu.created_at DESC
    LIMIT :limit
    """  # nosec: B608 - fixed column list, the stages are bound parameters
).bindparams(bindparam("stages", expanding=True))

_MISSING_UNITS_FOR_REQUEST = text(
    """
    SELECT iu.id AS information_id, iu.type, iu.content, iu.source_id,
           iu.document_id, iu.data_stage, iu.created_at
    FROM information_units AS iu
    JOIN documents AS d ON d.id = iu.document_id
    LEFT JOIN embeddings AS e
           ON e.owner_id = iu.id AND e.owner_type = :owner_type
    WHERE e.embedding_id IS NULL
      AND iu.deleted_at IS NULL
      AND iu.data_stage IN :stages
      AND d.request_id = :request_id
    ORDER BY iu.created_at DESC
    LIMIT :limit
    """  # nosec: B608 - fixed column list, the stages are bound parameters
).bindparams(bindparam("stages", expanding=True))


def to_embedding_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``embeddings`` row onto a reader-friendly dictionary.

    The vector itself is **not** returned: a report of what is indexed does not
    need 1 536 floats per row, and shipping them would make the delivery
    unreadable.
    """
    data = dict(row)
    return {
        "embedding_id": str(data.get("embedding_id") or ""),
        "owner_type": data.get("owner_type"),
        "owner_id": data.get("owner_id"),
        "model": data.get("model"),
        "dimensions": data.get("dimensions"),
        "metadata": as_dict(data.get("metadata")),
        "created_at": as_iso(data.get("created_at")),
    }


def to_unit_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``information_units`` row onto the §11 shape used for embedding."""
    data = dict(row)
    return {
        "information_id": data.get("information_id"),
        "type": data.get("type"),
        "content": as_dict(data.get("content")),
        "source_id": data.get("source_id"),
        "document_id": data.get("document_id"),
        "data_stage": data.get("data_stage"),
        "created_at": as_iso(data.get("created_at")),
    }


def _vector_literal(value: Any) -> str:
    """Return *value* as a pgvector literal, or raise ``ValueError``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts = [repr(float(item)) for item in value]
        if parts:
            return "[" + ",".join(parts) + "]"
    raise ValueError("an embedding row requires a non-empty vector")


def parse_vector(value: Any) -> list[float]:
    """Return the pgvector literal ``[a,b,c]`` of *value* as a list of floats.

    ``vector::text`` rend cette forme : la lire ainsi évite de dépendre du type
    ``vector`` côté Python (asyncpg le rend en texte), et un contenu illisible
    donne une liste vide — jamais une valeur inventée.
    """
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [float(item) for item in value]
    if not isinstance(value, str) or not value.strip():
        return []
    body = value.strip().strip("[]")
    if not body:
        return []
    parsed: list[float] = []
    for part in body.split(","):
        try:
            parsed.append(float(part))
        except ValueError:
            return []
    return parsed


class EmbeddingRepository:
    """§16.1 — the ``embeddings`` table, and the units still missing from it."""

    @classmethod
    async def insert_many(cls, engine: Any, rows: Sequence[Mapping[str, Any]]) -> int:
        """Insert *rows*, ignoring the identifiers already stored.

        Args:
            engine: Async engine connected to PostgreSQL with ``pgvector``.
            rows: One mapping per vector (``embedding_id``, ``owner_type``,
                ``owner_id``, ``model``, ``vector``, optional ``metadata``).

        Returns:
            The number of rows really inserted (``ON CONFLICT`` skips excluded).

        Raises:
            ValueError: When a row carries no ``owner_id``, no ``model`` or no
                vector — a vector nobody can attribute or trace back to a model
                would be worse than no vector at all (§0.2).
        """
        if not rows:
            return 0
        created_at = utc_now()
        prepared: list[dict[str, Any]] = []
        for row in rows:
            owner_id = str(row.get("owner_id") or "").strip()
            model = str(row.get("model") or "").strip()
            if not owner_id:
                raise ValueError("an embedding row requires an owner_id (§16.1)")
            if not model:
                raise ValueError(
                    "an embedding row requires the model that produced it "
                    f"(owner {owner_id})"
                )
            prepared.append(
                {
                    "embedding_id": str(row.get("embedding_id") or uuid.uuid4()),
                    "owner_type": str(row.get("owner_type") or "").strip()
                    or "information_unit",
                    "owner_id": owner_id,
                    "model": model,
                    "vector": _vector_literal(row.get("vector")),
                    "metadata": json.dumps(dict(row.get("metadata") or {})),
                    "created_at": created_at,
                }
            )
        inserted = 0
        async with engine.begin() as connection:
            for parameters in prepared:
                result = await connection.execute(_INSERT, parameters)
                rowcount = getattr(result, "rowcount", 0)
                inserted += int(rowcount) if isinstance(rowcount, int) and rowcount > 0 else 0
        return inserted

    @classmethod
    async def list_for_owner(
        cls,
        engine: Any,
        owner_type: str,
        owner_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return the vectors stored for one owner, newest first."""
        async with engine.connect() as connection:
            result = await connection.execute(
                _LIST_FOR_OWNER,
                {"owner_type": owner_type, "owner_id": owner_id, "limit": limit},
            )
            rows = result.mappings().all()
        return [to_embedding_response(row) for row in rows]

    @classmethod
    async def count(cls, engine: Any, owner_type: str = "information_unit") -> int:
        """Return how many vectors *owner_type* has."""
        async with engine.connect() as connection:
            result = await connection.execute(_COUNT, {"owner_type": owner_type})
            row = result.mappings().first()
        return int(row["total"]) if row else 0

    @classmethod
    async def get(cls, engine: Any, embedding_id: str) -> dict[str, Any] | None:
        """Return one stored vector **with its values**, or ``None`` (§16.1).

        Cette lecture est le point d'entrée du niveau **L3** du cache (§41.5) :
        c'est elle qui permet de réutiliser un vecteur déjà calculé au lieu de
        rappeler le fournisseur. Le vecteur est demandé en texte (``vector::text``)
        et rendu comme une liste de flottants — la représentation que le
        générateur sait réinsérer telle quelle.
        """
        async with engine.connect() as connection:
            result = await connection.execute(
                _SELECT_ONE, {"embedding_id": embedding_id}
            )
            row = result.mappings().first()
        if row is None:
            return None
        record = to_embedding_response(row)
        record["vector"] = parse_vector(row.get("vector"))
        return record

    @classmethod
    async def list_units_without_embedding(
        cls,
        engine: Any,
        *,
        owner_type: str = "information_unit",
        limit: int = 200,
        request_id: str | None = None,
        data_stages: Sequence[str] = DEFAULT_DATA_STAGES,
    ) -> list[dict[str, Any]]:
        """Return the §11 units of *data_stages* that have no vector yet.

        This is what ``scripts/backfill_embeddings.py`` walks: units with nothing
        stored for them, newest first, optionally restricted to one request
        (through the ``documents`` join, because ``information_units`` carries no
        ``request_id`` of its own).

        Args:
            engine: Async engine connected to PostgreSQL.
            owner_type: ``embeddings.owner_type`` used for the join.
            limit: Maximum number of units returned (§41.13).
            request_id: Restrict to the units ingested for that request.
            data_stages: §12 stages worth embedding; ``raw`` is excluded by
                default because it is untouched material.

        Returns:
            One §11 mapping per unit still missing from the index.
        """
        parameters: dict[str, Any] = {
            "owner_type": owner_type,
            "stages": [str(stage) for stage in data_stages],
            "limit": limit,
        }
        statement = _MISSING_UNITS
        if request_id:
            statement = _MISSING_UNITS_FOR_REQUEST
            parameters["request_id"] = request_id
        async with engine.connect() as connection:
            result = await connection.execute(statement, parameters)
            rows = result.mappings().all()
        return [to_unit_row(row) for row in rows]
